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
    parse_attendance_history_html,
    parse_attendance_report_html,
)
from tracy.domain.entities import Course, CourseModule


def test_service_data_decodes_moodle_nested_json() -> None:
    payload = '[{"error": false, "data": "{\\"courses\\": [{\\"id\\": 42}]}"}]'

    assert _service_data(json.loads(payload)) == {"courses": [{"id": 42}]}


@pytest.mark.asyncio
async def test_service_page_reads_response_before_navigation() -> None:
    class FakeResponse:
        url = "https://moodle.example/lib/ajax/service.php"
        status = 200

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
        status = 200

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
                    "Page.evaluate: Execution context was destroyed, most likely "
                    "because of a navigation"
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


@pytest.mark.asyncio
async def test_resource_fetch_handles_direct_download_response(tmp_path: Path) -> None:
    class FakeResponse:
        ok = True
        url = "https://moodle.example/pluginfile.php/1/course/slides.pdf"
        headers = {"content-type": "application/pdf"}

        async def body(self) -> bytes:
            return b"%PDF-test"

    class FakeRequest:
        async def get(self, url: str) -> FakeResponse:
            assert url == "https://moodle.example/mod/resource/view.php?id=57215"
            return FakeResponse()

    class FakeContext:
        request = FakeRequest()

    source = MoodleBrowserSource(
        base_url="https://moodle.example",
        profile_dir=tmp_path / "profile",
        data_dir=tmp_path,
    )
    module = CourseModule(
        id="57215",
        course_id="2834",
        section_id="18026",
        name="Unit I ppt",
        module_type="resource",
        source_url="https://moodle.example/mod/resource/view.php?id=57215",
    )

    documents = await source._fetch_resource_document(FakeContext(), module, "2834")

    assert len(documents) == 1
    assert documents[0].name == "slides.pdf"
    assert documents[0].local_path is not None
    assert documents[0].local_path.read_bytes() == b"%PDF-test"


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


def test_attendance_report_extracts_course_totals_and_percentage() -> None:
    html = """
    <table>
      <thead><tr>
        <th>Course Name</th><th>Total Sessions</th><th>Marked Sessions</th>
        <th>Attended Sessions</th><th>Percentage</th>
      </tr></thead>
      <tbody><tr>
        <td>Big Data Analytics 2026 June</td><td>23</td><td>23</td>
        <td>22</td><td>95.65%</td>
      </tr></tbody>
    </table>
    """

    summaries = parse_attendance_report_html(
        html,
        course_ids={"big data analytics 2026 june": "2803"},
        source_url="https://moodle.example/attendance-report/Student-Attendance/index.php",
    )

    assert len(summaries) == 1
    assert summaries[0].course_id == "2803"
    assert summaries[0].course_name == "Big Data Analytics 2026 June"
    assert summaries[0].total_sessions == 23
    assert summaries[0].marked_sessions == 23
    assert summaries[0].attended_sessions == 22
    assert summaries[0].percentage == 95.65


@pytest.mark.asyncio
async def test_attendance_report_fetch_uses_consolidated_report_url() -> None:
    class FakePage:
        def __init__(self) -> None:
            self.url: str | None = None

        async def goto(self, url: str, wait_until: str) -> None:
            self.url = url

        async def content(self) -> str:
            return """
            <table><tr>
              <th>Course Name</th><th>Total Sessions</th><th>Marked Sessions</th>
              <th>Attended Sessions</th><th>Percentage</th>
            </tr><tr>
              <td>DevOps Lab</td><td>10</td><td>10</td><td>8</td><td>80%</td>
            </tr></table>
            """

    source = MoodleBrowserSource(
        base_url="https://moodle.example",
        profile_dir=Path("data/browser-profile"),
        data_dir=Path("data"),
    )
    page = FakePage()

    summaries = await source._fetch_attendance_report(
        page, [Course(id="1", name="DevOps Lab")], RuntimeError
    )

    assert page.url == (
        "https://moodle.example/attendance-report/Student-Attendance/index.php"
    )
    assert summaries[0].course_id == "1"
    assert summaries[0].attended_sessions == 8


@pytest.mark.asyncio
async def test_attendance_report_restores_replacement_characters_from_course_data() -> None:
    canonical_name = "2023-27 – Sem – VII – Compiler Construction"
    report_name = canonical_name.replace("–", "\ufffd")

    class FakePage:
        async def goto(self, url: str, wait_until: str) -> None:
            return None

        async def content(self) -> str:
            return f"""
            <table><tr>
              <th>Course Name</th><th>Total Sessions</th><th>Marked Sessions</th>
              <th>Attended Sessions</th><th>Percentage</th>
            </tr><tr>
              <td>{report_name}</td><td>11</td><td>11</td><td>5</td><td>45.45%</td>
            </tr></table>
            """

    source = MoodleBrowserSource(
        base_url="https://moodle.example",
        profile_dir=Path("data/browser-profile"),
        data_dir=Path("data"),
    )

    summaries = await source._fetch_attendance_report(
        FakePage(), [Course(id="2834", name=canonical_name)], RuntimeError
    )

    assert summaries[0].course_id == "2834"
    assert summaries[0].course_name == canonical_name


@pytest.mark.asyncio
async def test_attendance_history_fetch_reads_visible_module() -> None:
    class FakePage:
        def __init__(self) -> None:
            self.urls: list[str] = []

        async def goto(self, url: str, wait_until: str) -> None:
            self.urls.append(url)

        async def content(self) -> str:
            return """
            <table><tr><th>Date</th><th>Status</th></tr>
            <tr><td>24 August 2026</td><td>Absent</td></tr></table>
            """

    source = MoodleBrowserSource(
        base_url="https://moodle.example",
        profile_dir=Path("data/browser-profile"),
        data_dir=Path("data"),
    )
    module = CourseModule(
        id="54501",
        course_id="2835",
        section_id="18030",
        name="B2",
        module_type="attendance",
        source_url="https://moodle.example/mod/attendance/view.php?id=54501",
    )

    records = await source._fetch_attendance_history(
        FakePage(),
        [(Course(id="2835", name="Compiler Construction Lab"), module)],
        RuntimeError,
    )

    assert len(records) == 1
    assert records[0].status == "Absent"
    assert records[0].course_id == "2835"


def test_attendance_history_extracts_session_date_status_and_remarks() -> None:
    html = """
    <table class="generaltable">
      <tr><th>Date</th><th>Description</th><th>Status</th><th>Remarks</th></tr>
      <tr>
        <td>Monday, 24 August 2026, 10:00 AM</td><td>Lecture</td>
        <td>Absent</td><td>Medical leave</td>
      </tr>
      <tr>
        <td>Monday, 31 August 2026, 10:00 AM</td><td>Lecture</td>
        <td>Present</td><td></td>
      </tr>
    </table>
    """

    records = parse_attendance_history_html(
        html,
        course_id="2835",
        course_name="Compiler Construction Lab",
        attendance_module_id="54501",
        attendance_module_name="B2",
        source_url="https://moodle.example/mod/attendance/view.php?id=54501",
        timezone="Asia/Kolkata",
    )

    assert len(records) == 2
    assert records[0].session_at == datetime(
        2026, 8, 24, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata")
    )
    assert records[0].status == "Absent"
    assert records[0].remarks == "Medical leave"
    assert records[0].attendance_module_name == "B2"
    assert records[1].status == "Present"


def test_attendance_history_extracts_moodle_date_time_range() -> None:
    html = """
    <table class="generaltable">
      <tr><th>Date</th><th>Description</th><th>Status</th><th>Points</th><th>Remarks</th></tr>
      <tr>
        <td>Mon 3 Aug 2026<br>2:30PM - 3:30PM</td>
        <td>Regular class session</td><td>Present</td><td>2 / 2</td><td></td>
      </tr>
    </table>
    """

    records = parse_attendance_history_html(
        html,
        course_id="2803",
        course_name="Big Data Analytics 2026 June",
        attendance_module_id="56567",
        attendance_module_name="BDA-1",
        source_url="https://moodle.example/mod/attendance/view.php?id=56567",
        timezone="Asia/Kolkata",
    )

    assert len(records) == 1
    assert records[0].session_at == datetime(
        2026, 8, 3, 14, 30, tzinfo=ZoneInfo("Asia/Kolkata")
    )
    assert records[0].description == "Regular class session"
