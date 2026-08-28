from datetime import UTC, datetime

import pytest

from tracy.application.create_reminders import create_reminders
from tracy.domain.entities import Assignment, Course, SyncSnapshot
from tracy.persistence.json_store import JsonSnapshotStore


@pytest.mark.asyncio
async def test_reminders_omit_assignments_already_submitted(tmp_path) -> None:
    JsonSnapshotStore(tmp_path).save(
        SyncSnapshot(
            synced_at=datetime(2026, 8, 29, tzinfo=UTC),
            courses=(Course(id="1", name="Databases"),),
            assignments=(
                Assignment(
                    id="submitted",
                    course_id="1",
                    name="Submitted CA",
                    due_at=datetime(2026, 8, 28, tzinfo=UTC),
                    submission_status="Submitted for grading",
                ),
                Assignment(
                    id="pending",
                    course_id="1",
                    name="Pending CA",
                    due_at=datetime(2026, 8, 30, tzinfo=UTC),
                    submission_status="No submissions have been made yet",
                ),
            ),
        )
    )

    report = await create_reminders(
        tmp_path,
        now=datetime(2026, 8, 29, tzinfo=UTC),
        timezone="UTC",
    )

    assert "Submitted CA" not in report
    assert "Pending CA" in report
