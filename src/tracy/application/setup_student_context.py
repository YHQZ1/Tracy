"""Collect local student context required for batch-aware Moodle answers."""

from collections.abc import Callable

from tracy.domain.entities import Course
from tracy.domain.student import LabBatch, StudentContext

Prompt = Callable[[str, str | None], str]


def _number(prompt: Prompt, message: str, allowed: set[int]) -> int:
    value = prompt(message, None).strip()
    options = ", ".join(map(str, sorted(allowed)))
    try:
        parsed = int(value)
    except ValueError as error:
        raise ValueError(f"Enter one of: {options}.") from error
    if parsed not in allowed:
        raise ValueError(f"Enter one of: {options}.")
    return parsed


def collect_student_context(courses: tuple[Course, ...], ask: Prompt) -> StudentContext:
    """Ask for identity, academic details, and batches for detected lab courses."""

    lab_courses = [
        course
        for course in courses
        if "lab" in course.name.casefold() or "practical" in course.name.casefold()
    ]
    lab_batches: list[LabBatch] = []
    context = StudentContext(
        name=ask("Full name", None),
        college_email=ask("College email", None),
        prn=ask("PRN", None),
        program=ask("Program / branch", None),
        division=ask("Division", None),
        year=_number(ask, "Year (1-4)", {1, 2, 3, 4}),
        semester=_number(ask, "Semester (1-8)", set(range(1, 9))),
    )
    for course in lab_courses:
        batch = ask(
            f"Lab batch for {course.name} (leave blank if not applicable)",
            "",
        ).strip()
        if batch:
            lab_batches.append(
                LabBatch(course_id=course.id, course_name=course.name, batch=batch)
            )
    return StudentContext(
        name=context.name,
        college_email=context.college_email,
        prn=context.prn,
        program=context.program,
        division=context.division,
        year=context.year,
        semester=context.semester,
        lab_batches=tuple(lab_batches),
    )
