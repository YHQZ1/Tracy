import asyncio
import inspect
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from tracy.adapters.moodle.browser import (
    MoodleBrowserSource,
    _service_data,
    parse_assignment_html,
)


def test_service_data_decodes_moodle_nested_json() -> None:
    payload = '[{"error": false, "data": "{\\"courses\\": [{\\"id\\": 42}]}"}]'

    assert _service_data(json.loads(payload)) == {"courses": [{"id": 42}]}


@pytest.mark.asyncio
async def test_service_page_reads_response_before_navigation() -> None:
    class FakeResponse:
        url = "https://moodle.example/lib/ajax/service.php"

        def __init__(self) -> None:
            self.navigated = False

        async def json(self) -> object:
            assert not self.navigated
            return [{"error": False, "data": '{"courses": [{"id": 42}]}'}]

    class FakeRoute:
        def __init__(self) -> None:
            self.response = FakeResponse()
            self.fulfilled = False

        async def fetch(self) -> FakeResponse:
            return self.response

        async def fulfill(self, *, response: FakeResponse) -> None:
            assert response is self.response
            self.fulfilled = True

        async def continue_(self) -> None:
            return None

    class FakePage:
        def __init__(self) -> None:
            self.routes: list[tuple[str, object]] = []

        async def route(self, pattern: str, callback: object) -> None:
            self.routes.append((pattern, callback))

        async def unroute(self, pattern: str, callback: object) -> None:
            self.routes.remove((pattern, callback))

        async def goto(self, url: str, wait_until: str) -> None:
            for pattern, callback in self.routes:
                if pattern != "**/lib/ajax/service.php*":
                    continue
                route = FakeRoute()
                result = callback(route)  # type: ignore[operator]
                if inspect.isawaitable(result):
                    await result
                assert route.fulfilled
                route.response.navigated = True

        async def wait_for_timeout(self, milliseconds: int) -> None:
            return None

    source = MoodleBrowserSource(
        base_url="https://moodle.example",
        profile_dir=Path("data/browser-profile"),
        data_dir=Path("data"),
    )

    assert await source._service_page(
        FakePage(),
        "https://moodle.example/my/",
        "core_course_get_enrolled_courses_by_timeline_classification",
        RuntimeError,
    ) == {"courses": [{"id": 42}]}


@pytest.mark.asyncio
async def test_service_page_waits_for_ajax_after_domcontentloaded() -> None:
    class FakeResponse:
        url = "https://moodle.example/lib/ajax/service.php"

        async def json(self) -> object:
            return [{"error": False, "data": '{"courses": [{"id": 42}]}'}]

    class FakeRoute:
        def __init__(self) -> None:
            self.response = FakeResponse()

        async def fetch(self) -> FakeResponse:
            return self.response

        async def fulfill(self, *, response: FakeResponse) -> None:
            return None

        async def continue_(self) -> None:
            return None

    class FakePage:
        def __init__(self) -> None:
            self.routes: list[tuple[str, object]] = []

        async def route(self, pattern: str, callback: object) -> None:
            self.routes.append((pattern, callback))

        async def unroute(self, pattern: str, callback: object) -> None:
            self.routes.remove((pattern, callback))

        async def goto(self, url: str, wait_until: str) -> None:
            async def emit_response() -> None:
                await asyncio.sleep(0)
                if self.routes:
                    result = self.routes[0][1](FakeRoute())  # type: ignore[operator]
                    if inspect.isawaitable(result):
                        await result

            asyncio.create_task(emit_response())

        async def wait_for_timeout(self, milliseconds: int) -> None:
            return None

    source = MoodleBrowserSource(
        base_url="https://moodle.example",
        profile_dir=Path("data/browser-profile"),
        data_dir=Path("data"),
        timeout_ms=100,
    )

    assert await source._service_page(
        FakePage(),
        "https://moodle.example/my/",
        "core_course_get_enrolled_courses_by_timeline_classification",
        RuntimeError,
    ) == {"courses": [{"id": 42}]}


@pytest.mark.asyncio
async def test_authentication_check_retries_navigation_context_reset() -> None:
    class FakePage:
        def __init__(self) -> None:
            self.attempts = 0

        async def evaluate(self, expression: str) -> int:
            self.attempts += 1
            if self.attempts == 1:
                raise RuntimeError(
                    "Page.evaluate: Execution context was destroyed, most likely because of a navigation"
                )
            return 42

        async def wait_for_timeout(self, milliseconds: int) -> None:
            return None

    source = MoodleBrowserSource(
        base_url="https://moodle.example",
        profile_dir=Path("data/browser-profile"),
        data_dir=Path("data"),
    )

    assert await source._is_authenticated(FakePage())


def test_assignment_html_extracts_dates_description_submission_and_files() -> None:
    html = """
    <html><head><title>Assignment 5 | Moodle</title></head><body>
      <a href="/pluginfile.php/1/core_admin/logo.png">logo.png</a>
      <div data-region="activity-information" data-activityname="Assignment 5">
        <div class="activity-dates">
          <div><strong>Opened:</strong> Friday, 14 August 2026, 12:00 AM</div>
          <div><strong>Due:</strong> Tuesday, 25 August 2026, 12:00 AM</div>
        </div>
      </div>
      <div id="intro"><p>Read the instructions.</p>
        <table><tr><td>Input</td><td>C</td></tr></table>
      </div>
      <div class="submissionstatustable"><table>
        <tr><th>Submission status</th><td>Submitted for grading</td></tr>
        <tr><th>Grading status</th><td>Not graded</td></tr>
        <tr><th>Last modified</th><td>Friday, 21 August 2026, 10:35 AM</td></tr>
        <tr><th>File submissions</th><td>
          <a href="/pluginfile.php/1/assignsubmission_file/submission_files/2/work.pdf">work.pdf</a>
        </td></tr>
      </table></div>
    </body></html>
    """

    assignment, files = parse_assignment_html(
        html,
        assignment_id="58976",
        course_id="2835",
        source_url="https://moodle.example/mod/assign/view.php?id=58976",
        fallback_name="Fallback",
        timezone="Asia/Kolkata",
    )

    assert assignment.name == "Assignment 5"
    assert assignment.due_at == datetime(2026, 8, 25, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert assignment.description == "Read the instructions. Input C"
    assert assignment.submission_status == "Submitted for grading"
    assert assignment.grading_status == "Not graded"
    assert assignment.last_modified_at is not None
    assert files == [
        "/pluginfile.php/1/assignsubmission_file/submission_files/2/work.pdf"
    ]


def test_assignment_dates_are_timezone_aware() -> None:
    html = (
        '<div data-region="activity-information" data-activityname="A">'
        '<div class="activity-dates">Due: 25 August 2026, 12:00 AM</div></div>'
    )

    assignment, _ = parse_assignment_html(
        html,
        assignment_id="1",
        course_id="2",
        source_url="https://moodle.example/assign/1",
        fallback_name="A",
        timezone="Asia/Kolkata",
    )

    assert assignment.due_at is not None
    assert assignment.due_at.utcoffset() is not None
