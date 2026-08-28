import json
from datetime import datetime
from zoneinfo import ZoneInfo

from tracy.adapters.moodle.browser import _service_data, parse_assignment_html


def test_service_data_decodes_moodle_nested_json() -> None:
    payload = '[{"error": false, "data": "{\\"courses\\": [{\\"id\\": 42}]}"}]'

    assert _service_data(json.loads(payload)) == {"courses": [{"id": 42}]}


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
