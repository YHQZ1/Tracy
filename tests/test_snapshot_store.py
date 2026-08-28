from datetime import UTC, date, datetime

from tracy.application.answer_question import _answer_from_snapshot
from tracy.domain.entities import Assignment, Course, SyncSnapshot
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
