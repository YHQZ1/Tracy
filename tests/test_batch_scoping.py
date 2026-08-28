from datetime import UTC, datetime

from tracy.application.query_plans import answer_from_query_plan
from tracy.domain.entities import Assignment, Course, CourseModule, CourseSection, SyncSnapshot
from tracy.domain.query import QueryPlan
from tracy.domain.student import LabBatch, StudentContext


def _context(batch: str) -> StudentContext:
    return StudentContext(
        name="Test Student",
        college_email="test@college.edu",
        prn="TEST123",
        program="Computer Science",
        division="B",
        year=4,
        semester=7,
        lab_batches=(LabBatch(course_id="bda", course_name="BDA Lab", batch=batch),),
    )


def _snapshot_with_batch_sections(include_general: bool = False) -> SyncSnapshot:
    sections = (
        CourseSection(id="l1", course_id="bda", number=1, title="Batch L1 (Tuesday)"),
        CourseSection(id="l2", course_id="bda", number=2, title="Batch L2 (Tuesday)"),
    )
    modules = (
        CourseModule(
            id="l1-exp1",
            course_id="bda",
            section_id="l1",
            name="Experiment No 1",
            module_type="assign",
        ),
        CourseModule(
            id="l2-exp1",
            course_id="bda",
            section_id="l2",
            name="Experiment No 1",
            module_type="assign",
        ),
    )
    assignments = (
        Assignment(id="l1-exp1", course_id="bda", name="Experiment No 1"),
        Assignment(id="l2-exp1", course_id="bda", name="Experiment No 1"),
    )
    if include_general:
        sections += (CourseSection(id="general", course_id="bda", number=0, title="General"),)
        modules += (
            CourseModule(
                id="general-exp1",
                course_id="bda",
                section_id="general",
                name="Experiment No 1",
                module_type="assign",
            ),
        )
        assignments += (Assignment(id="general-exp1", course_id="bda", name="Experiment No 1"),)
    return SyncSnapshot(
        synced_at=datetime.now(UTC),
        courses=(Course(id="bda", name="BDA Lab"),),
        sections=sections,
        modules=modules,
        assignments=assignments,
    )


def test_batch_specific_activity_matches_saved_batch() -> None:
    answer = answer_from_query_plan(
        QueryPlan(intent="assignments"),
        _snapshot_with_batch_sections(),
        student_context=_context("L1"),
    )

    assert answer is not None
    assert answer.count("Experiment No 1") == 1
    assert "l1-exp1" not in answer
    assert "l2-exp1" not in answer


def test_general_activity_is_fallback_when_no_specific_batch_matches() -> None:
    answer = answer_from_query_plan(
        QueryPlan(intent="assignments"),
        _snapshot_with_batch_sections(include_general=True),
        student_context=_context("L3"),
    )

    assert answer is not None
    assert answer.count("Experiment No 1") == 1
