from datetime import UTC, date, datetime

import pytest

from tracy.application.answer_question import _answer_from_snapshot, answer_question
from tracy.application.query_plans import answer_from_query_plan
from tracy.domain.entities import Assignment, AttendanceSummary, Course, SyncSnapshot
from tracy.domain.query import QueryPlan
from tracy.persistence.json_store import JsonSnapshotStore


def test_snapshot_round_trip_and_structured_answers(tmp_path) -> None:
    snapshot = SyncSnapshot(
        synced_at=datetime.now(UTC),
        courses=(Course(id="1", name="Databases"),),
        assignments=(
            Assignment(
                id="2",
                course_id="1",
                name="CA",
                due_at=datetime(2026, 8, 25, tzinfo=UTC),
                source_url="https://moodle.example/assign/2",
            ),
        ),
        attendance=(
            AttendanceSummary(
                course_id="1",
                course_name="Databases",
                total_sessions=23,
                marked_sessions=23,
                attended_sessions=22,
                percentage=95.65,
                source_url="https://moodle.example/attendance-report",
            ),
        ),
    )
    store = JsonSnapshotStore(tmp_path)

    store.save(snapshot)
    loaded = store.load()

    assert loaded == snapshot
    assert "Databases" in _answer_from_snapshot("list my courses", loaded)
    assert "CA" in _answer_from_snapshot("what assignments are due?", loaded)


def test_this_week_assignments_exclude_past_dates_and_show_course() -> None:
    snapshot = SyncSnapshot(
        synced_at=datetime.now(UTC),
        courses=(Course(id="1", name="Databases"),),
        assignments=(
            Assignment(
                id="past",
                course_id="1",
                name="Past CA",
                due_at=datetime(2026, 8, 25, tzinfo=UTC),
            ),
            Assignment(
                id="upcoming",
                course_id="1",
                name="Upcoming CA",
                due_at=datetime(2026, 8, 30, tzinfo=UTC),
            ),
        ),
    )

    answer = _answer_from_snapshot(
        "what assignments are due this week?", snapshot, today=date(2026, 8, 28)
    )

    assert "Upcoming CA" in answer
    assert "Past CA" not in answer
    assert "Databases" in answer

    historical_answer = _answer_from_snapshot(
        "what assignments were due this week?", snapshot, today=date(2026, 8, 28)
    )

    assert "Past CA" in historical_answer
    assert "Databases" in historical_answer


def test_course_filter_ignores_punctuation_and_selects_one_course() -> None:
    snapshot = SyncSnapshot(
        synced_at=datetime.now(UTC),
        courses=(
            Course(id="theory", name="2023-27 – Sem – VII – Compiler Construction"),
            Course(id="lab", name="2023-27 – Sem – VII – Compiler Construction - Lab"),
        ),
        assignments=(
            Assignment(id="theory-ca", course_id="theory", name="Theory CA"),
            Assignment(id="lab-ca", course_id="lab", name="Lab Assignment 1"),
        ),
    )

    answer = answer_from_query_plan(
        QueryPlan(intent="assignments", course_query="Compiler Construction Lab"),
        snapshot,
    )

    assert "Lab Assignment 1" in answer
    assert "Theory CA" not in answer


def test_attendance_answer_is_course_scoped_and_deterministic() -> None:
    snapshot = SyncSnapshot(
        synced_at=datetime.now(UTC),
        courses=(
            Course(id="1", name="Databases"),
            Course(id="2", name="DevOps Lab"),
        ),
        attendance=(
            AttendanceSummary(
                course_id="1",
                course_name="Databases",
                total_sessions=20,
                marked_sessions=20,
                attended_sessions=18,
                percentage=90.0,
            ),
            AttendanceSummary(
                course_id="2",
                course_name="DevOps Lab",
                total_sessions=12,
                marked_sessions=12,
                attended_sessions=9,
                percentage=75.0,
            ),
        ),
    )

    answer = answer_from_query_plan(
        QueryPlan(intent="attendance", course_query="DevOps Lab"), snapshot
    )

    assert answer == (
        "Attendance:\n"
        "- DevOps Lab — 9/12 attended, 12 marked (75.00%)"
    )


def test_offline_attendance_question_infers_course() -> None:
    snapshot = SyncSnapshot(
        synced_at=datetime.now(UTC),
        courses=(Course(id="1", name="DevOps Lab"),),
        attendance=(
            AttendanceSummary(
                course_id="1",
                course_name="DevOps Lab",
                total_sessions=12,
                marked_sessions=12,
                attended_sessions=9,
                percentage=75.0,
            ),
        ),
    )

    answer = _answer_from_snapshot("What is my attendance in DevOps Lab?", snapshot)

    assert "DevOps Lab" in answer
    assert "9/12" in answer


def test_overall_attendance_uses_total_sessions_as_denominator() -> None:
    snapshot = SyncSnapshot(
        synced_at=datetime.now(UTC),
        courses=(
            Course(id="1", name="Databases"),
            Course(id="2", name="DevOps Lab"),
            Course(id="3", name="Project"),
        ),
        attendance=(
            AttendanceSummary(
                course_id="1",
                course_name="Databases",
                total_sessions=10,
                marked_sessions=8,
                attended_sessions=6,
                percentage=75.0,
            ),
            AttendanceSummary(
                course_id="2",
                course_name="DevOps Lab",
                total_sessions=5,
                marked_sessions=5,
                attended_sessions=5,
                percentage=100.0,
            ),
            AttendanceSummary(
                course_id="3",
                course_name="Project",
                total_sessions=0,
                marked_sessions=0,
                attended_sessions=0,
                percentage=None,
            ),
        ),
    )

    answer = answer_from_query_plan(
        QueryPlan(intent="attendance", group_by="overall"), snapshot
    )

    assert answer == "Overall attendance: 11/15 total sessions attended (73.33%)"


class StaticPlanner:
    def __init__(self, plan: QueryPlan) -> None:
        self.plan_value = plan

    async def plan(self, question: str, course_names: tuple[str, ...] = ()) -> QueryPlan:
        return self.plan_value


@pytest.mark.asyncio
async def test_answer_question_recovers_course_filter_when_planner_omits_it(tmp_path) -> None:
    JsonSnapshotStore(tmp_path).save(
        SyncSnapshot(
            synced_at=datetime.now(UTC),
            courses=(
                Course(id="theory", name="2023-27 – Sem – VII – Compiler Construction"),
                Course(id="lab", name="2023-27 – Sem – VII – Compiler Construction - Lab"),
            ),
            assignments=(
                Assignment(id="theory-ca", course_id="theory", name="Theory CA"),
                Assignment(id="lab-ca", course_id="lab", name="Lab Assignment 1"),
            ),
        )
    )

    answer = await answer_question(
        "List all assignments for Compiler Construction Lab, sorted by due date.",
        tmp_path,
        planner=StaticPlanner(QueryPlan(intent="assignments")),
    )

    assert "Lab Assignment 1" in answer
    assert "Theory CA" not in answer


@pytest.mark.asyncio
async def test_answer_question_executes_assignment_query_plan(tmp_path) -> None:
    JsonSnapshotStore(tmp_path).save(
        SyncSnapshot(
            synced_at=datetime.now(UTC),
            courses=(Course(id="1", name="Databases"),),
            assignments=(
                Assignment(
                    id="past",
                    course_id="1",
                    name="Past CA",
                    due_at=datetime(2026, 8, 25, tzinfo=UTC),
                    cutoff_at=datetime(2026, 8, 26, tzinfo=UTC),
                    submission_status="Submitted",
                ),
                Assignment(
                    id="upcoming",
                    course_id="1",
                    name="Upcoming CA",
                    due_at=datetime(2026, 8, 30, tzinfo=UTC),
                    cutoff_at=datetime(2026, 8, 31, tzinfo=UTC),
                    submission_status="Not submitted",
                ),
            ),
        )
    )
    planner = StaticPlanner(
        QueryPlan(
            intent="assignments",
            time_range="next_7_days",
            direction="upcoming",
            fields=("due_date", "cutoff_date", "submission_status"),
            group_by="course",
        )
    )

    answer = await answer_question(
        "For every upcoming assignment, show the due date and status.",
        tmp_path,
        planner=planner,
    )
    assert "Databases:" in answer
    assert "Upcoming CA" in answer
    assert "Sun, 30 Aug 2026" in answer
    assert "cutoff: Mon, 31 Aug 2026" in answer
    assert "status: Not submitted" in answer
    assert "Past CA" not in answer


@pytest.mark.asyncio
async def test_answer_question_recovers_overall_attendance_grouping(tmp_path) -> None:
    JsonSnapshotStore(tmp_path).save(
        SyncSnapshot(
            synced_at=datetime.now(UTC),
            courses=(Course(id="1", name="Databases"),),
            attendance=(
                AttendanceSummary(
                    course_id="1",
                    course_name="Databases",
                    total_sessions=10,
                    marked_sessions=8,
                    attended_sessions=6,
                    percentage=75.0,
                ),
            ),
        )
    )

    answer = await answer_question(
        "What is my overall attendance?",
        tmp_path,
        planner=StaticPlanner(QueryPlan(intent="attendance")),
    )

    assert answer == "Overall attendance: 6/10 total sessions attended (60.00%)"
