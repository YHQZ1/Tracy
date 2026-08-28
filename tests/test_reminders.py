from datetime import UTC, datetime

import pytest

from tracy.application.create_reminders import create_reminders
from tracy.domain.entities import Assignment, Course, CourseModule, CourseSection, SyncSnapshot
from tracy.domain.student import LabBatch, StudentContext
from tracy.persistence.json_store import JsonSnapshotStore
from tracy.persistence.student_context_store import JsonStudentContextStore


def _context() -> StudentContext:
    return StudentContext(
        name="Test Student",
        college_email="test@college.edu",
        prn="TEST123",
        program="Computer Science",
        division="B",
        year=4,
        semester=7,
        lab_batches=(LabBatch(course_id="bda", course_name="BDA Lab", batch="L1"),),
    )


@pytest.mark.asyncio
async def test_reminders_show_overdue_and_upcoming_assignments_with_context(tmp_path) -> None:
    JsonSnapshotStore(tmp_path).save(
        SyncSnapshot(
            synced_at=datetime(2026, 8, 29, tzinfo=UTC),
            courses=(Course(id="bda", name="BDA Lab"),),
            sections=(
                CourseSection(id="general", course_id="bda", number=0, title="General"),
                CourseSection(id="l1", course_id="bda", number=1, title="Batch L1"),
                CourseSection(id="l2", course_id="bda", number=2, title="Batch L2"),
            ),
            modules=(
                CourseModule(
                    id="general-ca",
                    course_id="bda",
                    section_id="general",
                    name="CA",
                    module_type="assign",
                ),
                CourseModule(
                    id="l1-exp",
                    course_id="bda",
                    section_id="l1",
                    name="Experiment 1",
                    module_type="assign",
                ),
                CourseModule(
                    id="l2-exp",
                    course_id="bda",
                    section_id="l2",
                    name="Experiment 1",
                    module_type="assign",
                ),
            ),
            assignments=(
                Assignment(
                    id="general-ca",
                    course_id="bda",
                    name="CA",
                    due_at=datetime(2026, 8, 25, 12, tzinfo=UTC),
                    cutoff_at=datetime(2026, 8, 26, 12, tzinfo=UTC),
                    submission_status="Not submitted",
                    source_url="https://moodle.example/assign/general-ca",
                ),
                Assignment(
                    id="l1-exp",
                    course_id="bda",
                    name="Experiment 1",
                    due_at=datetime(2026, 8, 30, 12, tzinfo=UTC),
                    submission_status="Not submitted",
                    source_url="https://moodle.example/assign/l1-exp",
                ),
                Assignment(
                    id="l2-exp",
                    course_id="bda",
                    name="Experiment 1",
                    due_at=datetime(2026, 8, 30, 12, tzinfo=UTC),
                    source_url="https://moodle.example/assign/l2-exp",
                ),
            ),
        )
    )
    JsonStudentContextStore(tmp_path).save(_context())

    report = await create_reminders(
        tmp_path,
        now=datetime(2026, 8, 29, 9, tzinfo=UTC),
        timezone="UTC",
    )

    assert "Overdue assignments:" in report
    assert "CA — BDA Lab" in report
    assert "cutoff: Wed, 26 Aug 2026 at 12:00 PM" in report
    assert "status: Not submitted" in report
    assert "Due in the next 7 days:" in report
    assert "Experiment 1 — BDA Lab" in report
    assert "l1-exp" in report
    assert "l2-exp" not in report


@pytest.mark.asyncio
async def test_reminders_do_not_treat_undated_assignments_as_actionable(tmp_path) -> None:
    JsonSnapshotStore(tmp_path).save(
        SyncSnapshot(
            synced_at=datetime(2026, 8, 29, tzinfo=UTC),
            courses=(Course(id="1", name="Databases"),),
            assignments=(Assignment(id="1", course_id="1", name="Reading", due_at=None),),
        )
    )

    report = await create_reminders(
        tmp_path,
        now=datetime(2026, 8, 29, tzinfo=UTC),
        timezone="UTC",
    )

    assert "No assignments are overdue or due in the next 7 days." in report
    assert "1 assignment has no due date" in report
