from datetime import UTC, datetime

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
