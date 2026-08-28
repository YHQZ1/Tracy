"""Moodle browser-session adapter.

The university Moodle instance does not expose student-created API tokens, so
this adapter uses a dedicated Playwright profile. The user signs in manually
once; subsequent syncs reuse the local authenticated session.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlparse
from zoneinfo import ZoneInfo

from tracy.domain.entities import (
    Assignment,
    Course,
    CourseModule,
    CourseSection,
    Document,
    SyncSnapshot,
)


class MoodleConnectionError(RuntimeError):
    """Raised when the authenticated Moodle session cannot be used."""


class MoodleLoginRequired(MoodleConnectionError):
    """Raised when the dedicated browser profile needs a manual login."""


def _absolute_url(base_url: str, value: str | None) -> str | None:
    if not value:
        return None
    return urljoin(f"{base_url.rstrip('/')}/", value)


def _epoch(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=UTC)
    except (TypeError, ValueError, OSError):
        return None


def _clean_text(value: str) -> str:
    return " ".join(value.split())


def _decode_data(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _service_data(payload: Any) -> Any:
    """Unwrap Moodle's batch response and its nested JSON data field."""

    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict) and item.get("error"):
                raise MoodleConnectionError(str(item.get("exception", item)))
            if isinstance(item, dict) and "data" in item:
                return _decode_data(item["data"])
        return payload
    return _decode_data(payload)


class MoodleHtmlParser(HTMLParser):
    """Extract semantic blocks, links, and table rows from Moodle HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: dict[str, list[str]] = {"dates": [], "intro": [], "submission": []}
        self.links: list[tuple[str, str]] = []
        self.submission_links: list[str] = []
        self.rows: list[list[str]] = []
        self.activity_name: str | None = None
        self.title_parts: list[str] = []
        self._active_blocks: list[tuple[str, int]] = []
        self._depth = 0
        self._in_title = False
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._anchor_href: str | None = None
        self._anchor_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())

        if tag == "title":
            self._in_title = True
        if tag == "a":
            self._anchor_href = attributes.get("href")
            self._anchor_text = []
        if tag == "tr":
            self._row = []
        if tag in {"th", "td"} and self._row is not None:
            self._cell = []

        if attributes.get("data-activityname"):
            self.activity_name = attributes["data-activityname"]
        if attributes.get("id") == "intro":
            self._active_blocks.append(("intro", self._depth))
        if "activity-dates" in classes:
            self._active_blocks.append(("dates", self._depth))
        if "submissionstatustable" in classes:
            self._active_blocks.append(("submission", self._depth))

        self._depth += 1

    def handle_endtag(self, tag: str) -> None:
        self._depth = max(0, self._depth - 1)

        if tag in {"th", "td"} and self._row is not None and self._cell is not None:
            self._row.append(_clean_text(" ".join(self._cell)))
            self._cell = None
        if tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None
        if tag == "a" and self._anchor_href:
            link_text = _clean_text(" ".join(self._anchor_text))
            self.links.append((self._anchor_href, link_text))
            if any(block == "submission" for block, _ in self._active_blocks):
                self.submission_links.append(self._anchor_href)
            self._anchor_href = None
            self._anchor_text = []
        if tag == "title":
            self._in_title = False

        while self._active_blocks and self._active_blocks[-1][1] == self._depth:
            self._active_blocks.pop()

    def handle_data(self, data: str) -> None:
        if not data.strip():
            return
        if self._in_title:
            self.title_parts.append(data)
        if self._anchor_href:
            self._anchor_text.append(data)
        if self._cell is not None:
            self._cell.append(data)
        for block, _ in self._active_blocks:
            self.blocks[block].append(data)


def _parse_local_datetime(value: str | None, timezone: str) -> datetime | None:
    if not value:
        return None
    value = _clean_text(value)
    formats = (
        "%A, %d %B %Y, %I:%M %p",
        "%d %B %Y, %I:%M %p",
        "%A, %d %B %Y %I:%M %p",
        "%d %B %Y %I:%M %p",
    )
    for date_format in formats:
        try:
            return datetime.strptime(value, date_format).replace(tzinfo=ZoneInfo(timezone))
        except ValueError:
            continue
    return None


def _label_value(rows: list[list[str]], label: str) -> str | None:
    for row in rows:
        if len(row) >= 2 and row[0].rstrip(":").casefold() == label.casefold():
            return row[1]
    return None


def _date_value(text: str, label: str, following_labels: tuple[str, ...]) -> str | None:
    boundary = "|".join(re.escape(item) for item in following_labels)
    lookahead = rf"(?=\s+(?:{boundary})\s*:|$)" if boundary else r"(?=$)"
    match = re.search(
        rf"{re.escape(label)}\s*:?\s*(.*?){lookahead}",
        text,
        flags=re.IGNORECASE,
    )
    return _clean_text(match.group(1)) if match else None


def parse_assignment_html(
    html: str,
    *,
    assignment_id: str,
    course_id: str,
    source_url: str,
    fallback_name: str,
    timezone: str,
) -> tuple[Assignment, list[str]]:
    """Parse one authenticated ``mod/assign/view.php`` page."""

    parser = MoodleHtmlParser()
    parser.feed(html)
    dates = _clean_text(" ".join(parser.blocks["dates"]))
    submission = parser.blocks["submission"]
    assignment = Assignment(
        id=assignment_id,
        course_id=course_id,
        name=parser.activity_name or fallback_name or _clean_text(" ".join(parser.title_parts)),
        opened_at=_parse_local_datetime(
            _date_value(dates, "Opened", ("Due", "Cut-off date", "Cut-off")), timezone
        ),
        due_at=_parse_local_datetime(
            _date_value(dates, "Due", ("Cut-off date", "Cut-off")), timezone
        ),
        cutoff_at=_parse_local_datetime(
            _date_value(dates, "Cut-off date", ()), timezone
        )
        or _parse_local_datetime(_date_value(dates, "Cut-off", ()), timezone),
        source_url=source_url,
        description=_clean_text(" ".join(parser.blocks["intro"])) or None,
        submission_status=_label_value(parser.rows, "Submission status"),
        grading_status=_label_value(parser.rows, "Grading status"),
        last_modified_at=_parse_local_datetime(
            _label_value(parser.rows, "Last modified"), timezone
        ),
    )
    file_urls = [href for href in parser.submission_links if "pluginfile.php" in href]
    return assignment, file_urls


class MoodleBrowserSource:
    """Read Moodle through a persistent, manually authenticated browser profile."""

    def __init__(
        self,
        *,
        base_url: str,
        profile_dir: Path,
        data_dir: Path,
        headless: bool = False,
        timezone: str = "Asia/Kolkata",
        timeout_ms: int = 30_000,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.profile_dir = profile_dir
        self.data_dir = data_dir
        self.headless = headless
        self.timezone = timezone
        self.timeout_ms = timeout_ms

    async def sync(self) -> SyncSnapshot:
        try:
            from playwright.async_api import TimeoutError as PlaywrightTimeoutError
            from playwright.async_api import async_playwright
        except ModuleNotFoundError as error:
            raise MoodleConnectionError(
                "Browser support is not installed. Run `uv sync --extra browser` "
                "and `uv run playwright install chromium`."
            ) from error

        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                headless=self.headless,
            )
            try:
                page = context.pages[0] if context.pages else await context.new_page()
                await self._ensure_authenticated(page)
                courses = await self._fetch_courses(page, PlaywrightTimeoutError)
                sections: list[CourseSection] = []
                modules: list[CourseModule] = []
                assignments: list[Assignment] = []
                documents: list[Document] = []

                for course in courses:
                    state = await self._fetch_course_state(page, course.id, PlaywrightTimeoutError)
                    course_sections, course_modules = self._parse_course_state(course.id, state)
                    sections.extend(course_sections)
                    modules.extend(course_modules)

                    for module in course_modules:
                        if not module.user_visible or not module.source_url:
                            continue
                        if module.module_type == "assign":
                            assignment, submission_files = await self._fetch_assignment(
                                page, module, course.id, PlaywrightTimeoutError
                            )
                            assignments.append(assignment)
                            documents.extend(
                                await self._download_files(
                                    context,
                                    submission_files,
                                    course.id,
                                    f"assignment-{module.id}",
                                    page,
                                )
                            )
                        elif module.module_type in {"resource", "file"}:
                            documents.extend(
                                await self._fetch_resource_document(
                                    context, page, module, course.id, PlaywrightTimeoutError
                                )
                            )

                return SyncSnapshot(
                    synced_at=datetime.now(tz=UTC),
                    courses=tuple(courses),
                    sections=tuple(sections),
                    modules=tuple(modules),
                    assignments=tuple(assignments),
                    documents=tuple(documents),
                )
            finally:
                await context.close()

    async def _ensure_authenticated(self, page: Any) -> None:
        await page.goto(f"{self.base_url}/my/", wait_until="domcontentloaded")
        if not await self._is_authenticated(page):
            if self.headless:
                raise MoodleLoginRequired(
                    "The Moodle browser profile is not signed in. Run sync once with "
                    "TRACY_MOODLE_HEADLESS=false and sign in manually."
                )
            print("Log into Moodle in the opened browser window, then return here.")
            await asyncio.to_thread(input, "Press Enter after Moodle is open: ")
            await page.goto(f"{self.base_url}/my/", wait_until="domcontentloaded")
            if not await self._is_authenticated(page):
                raise MoodleLoginRequired("Moodle login was not completed.")

    async def _is_authenticated(self, page: Any) -> bool:
        """Use Moodle's own runtime config instead of guessing the login page URL."""

        user_id = await page.evaluate("() => window.M?.cfg?.userId || 0")
        return bool(user_id)

    @staticmethod
    def _service_result_matches(method: str, data: Any) -> bool:
        if not isinstance(data, dict):
            return False
        if method == "core_course_get_enrolled_courses_by_timeline_classification":
            return isinstance(data.get("courses"), list)
        if method == "core_courseformat_get_state":
            return isinstance(data.get("cm"), list) and isinstance(data.get("section"), list)
        return True

    async def _service_page(self, page: Any, url: str, method: str, timeout_error: Any) -> Any:
        responses: list[tuple[str, Any]] = []
        tasks: list[Any] = []

        async def read_response(response: Any) -> None:
            try:
                payload = json.loads(await response.text())
                responses.append((response.url, _service_data(payload)))
            except (json.JSONDecodeError, MoodleConnectionError):
                return

        def capture_response(response: Any) -> None:
            if "/lib/ajax/service.php" in response.url:
                tasks.append(asyncio.create_task(read_response(response)))

        page.on("response", capture_response)

        try:
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_timeout(750)
            if tasks:
                await asyncio.gather(*tasks)
        except timeout_error as error:
            raise MoodleConnectionError(
                f"Moodle did not return the expected AJAX function {method} while loading {url}."
            ) from error
        finally:
            page.remove_listener("response", capture_response)

        for response_url, data in responses:
            if method in unquote(response_url) or self._service_result_matches(method, data):
                return data
        raise MoodleConnectionError(
            f"Moodle did not return the expected AJAX function {method} while loading {url}."
        )

    async def _fetch_courses(self, page: Any, timeout_error: Any) -> list[Course]:
        data = await self._service_page(
            page,
            f"{self.base_url}/my/",
            "core_course_get_enrolled_courses_by_timeline_classification",
            timeout_error,
        )
        return [
            Course(
                id=str(item["id"]),
                name=item.get("fullname") or item.get("fullnamedisplay") or "Unnamed course",
                code=item.get("shortname") or item.get("idnumber"),
                start_at=_epoch(item.get("startdate")),
                end_at=_epoch(item.get("enddate")),
                source_url=_absolute_url(self.base_url, item.get("viewurl")),
                category=item.get("coursecategory"),
                progress=item.get("progress"),
            )
            for item in data.get("courses", [])
        ]

    async def _fetch_course_state(
        self, page: Any, course_id: str, timeout_error: Any
    ) -> dict[str, Any]:
        data = await self._service_page(
            page,
            f"{self.base_url}/course/view.php?id={course_id}",
            "core_courseformat_get_state",
            timeout_error,
        )
        return data if isinstance(data, dict) else {}

    def _parse_course_state(
        self, course_id: str, state: dict[str, Any]
    ) -> tuple[list[CourseSection], list[CourseModule]]:
        sections = [
            CourseSection(
                id=str(item["id"]),
                course_id=course_id,
                number=int(item.get("section", 0)),
                title=item.get("title") or f"Section {item.get('section', 0)}",
            )
            for item in state.get("section", [])
        ]
        modules = [
            CourseModule(
                id=str(item["id"]),
                course_id=course_id,
                section_id=str(item.get("sectionid", "")),
                name=item.get("name") or "Unnamed activity",
                module_type=(item.get("module") or item.get("modname") or "").lower(),
                source_url=_absolute_url(self.base_url, item.get("url")),
                user_visible=bool(item.get("uservisible", False)),
                restricted=bool(item.get("hascmrestrictions", False)),
            )
            for item in state.get("cm", [])
        ]
        return sections, modules

    async def _fetch_assignment(
        self, page: Any, module: CourseModule, course_id: str, timeout_error: Any
    ) -> tuple[Assignment, list[str]]:
        try:
            await page.goto(module.source_url, wait_until="domcontentloaded")
        except timeout_error:
            raise MoodleConnectionError(f"Timed out loading assignment {module.id}.")
        html = await page.content()
        return parse_assignment_html(
            html,
            assignment_id=module.id,
            course_id=course_id,
            source_url=module.source_url or "",
            fallback_name=module.name,
            timezone=self.timezone,
        )

    async def _fetch_resource_document(
        self, context: Any, page: Any, module: CourseModule, course_id: str, timeout_error: Any
    ) -> list[Document]:
        try:
            await page.goto(module.source_url, wait_until="domcontentloaded")
        except timeout_error:
            raise MoodleConnectionError(f"Timed out loading resource {module.id}.")
        file_urls: list[str] = []
        if "pluginfile.php" in page.url:
            file_urls.append(page.url)
        else:
            parser = MoodleHtmlParser()
            parser.feed(await page.content())
            file_urls.extend(href for href, _ in parser.links if "pluginfile.php" in href)
        return await self._download_files(context, file_urls, course_id, module.name, page)

    async def _download_files(
        self,
        context: Any,
        file_urls: list[str],
        course_id: str,
        label: str,
        page: Any,
    ) -> list[Document]:
        documents: list[Document] = []
        for index, file_url in enumerate(dict.fromkeys(file_urls), start=1):
            absolute_file_url = _absolute_url(self.base_url, file_url)
            if not absolute_file_url:
                continue
            response = await context.request.get(absolute_file_url)
            if not response.ok:
                continue
            content = await response.body()
            digest = hashlib.sha256(content).hexdigest()
            filename = Path(urlparse(absolute_file_url).path).name or f"{label}-{index}"
            filename = re.sub(r"[^A-Za-z0-9._-]+", "_", unquote(filename))
            destination = self.data_dir / "documents" / course_id / filename
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
            documents.append(
                Document(
                    id=f"{course_id}:{digest}",
                    course_id=course_id,
                    name=filename,
                    source_url=absolute_file_url,
                    content_hash=digest,
                    local_path=destination,
                    content_type=response.headers.get("content-type"),
                )
            )
        return documents
