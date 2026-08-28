"""Heuristics and deterministic execution for validated Moodle query plans."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from tracy.domain.entities import Assignment, SyncSnapshot
from tracy.domain.query import QueryPlan


def heuristic_query_plan(question: str) -> QueryPlan:
    """Provide an offline plan when the local planner is unavailable."""

    normalized = question.casefold()
    if "assignment" in normalized or "deadline" in normalized or "due" in normalized:
        if "next seven" in normalized or "next 7" in normalized:
            time_range = "next_7_days"
            direction = "upcoming"
        elif "this week" in normalized:
            time_range = "this_week"
            direction = (
                "past" if "were due" in normalized or "was due" in normalized else "upcoming"
            )
        elif "overdue" in normalized or "past due" in normalized:
            time_range = "overdue"
            direction = "past"
        elif "upcoming" in normalized or "soon" in normalized:
            time_range = "upcoming"
            direction = "upcoming"
        else:
            time_range = "all"
            direction = "all"
        fields = ["due_date"]
        if "cutoff" in normalized:
            fields.append("cutoff_date")
        if "status" in normalized or "submitted" in normalized:
            fields.append("submission_status")
        return QueryPlan(
            intent="assignments",
            time_range=time_range,
            direction=direction,
            fields=tuple(fields),
            group_by=(
                "course"
                if "grouped by course" in normalized or "by course" in normalized
                else None
            ),
        )
    if "enrolled" in normalized or "list my courses" in normalized:
        return QueryPlan(intent="courses")
    return QueryPlan(intent="documents")


def _format_assignment(
    assignment: Assignment,
    course_name: str,
    fields: frozenset[str],
    *,
    include_course: bool = True,
) -> str:
    due = (
        assignment.due_at.strftime("%a, %d %b %Y at %I:%M %p")
        if assignment.due_at
        else "no due date"
    )
    parts = [f"- {assignment.name} — {due}"]
    if "cutoff_date" in fields:
        cutoff = (
            assignment.cutoff_at.strftime("%a, %d %b %Y at %I:%M %p")
            if assignment.cutoff_at
            else "no cutoff date"
        )
        parts.append(f"cutoff: {cutoff}")
    if "submission_status" in fields:
        parts.append(f"status: {assignment.submission_status or 'not available'}")
    if assignment.source_url:
        parts.append(f"source: {assignment.source_url}")
    formatted = " — ".join(parts)
    return f"{course_name}: {formatted}" if include_course else formatted


def _assignment_matches_time(
    assignment: Assignment, plan: QueryPlan, today: date
) -> bool:
    if assignment.due_at is None:
        return plan.time_range == "all"
    due_date = assignment.due_at.date()
    if plan.time_range == "overdue":
        return due_date < today
    if plan.time_range == "next_7_days":
        return today <= due_date < today + timedelta(days=7)
    if plan.time_range == "upcoming":
        return due_date >= today
    if plan.time_range == "this_week":
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=7)
        if plan.direction == "past":
            return week_start <= due_date <= today
        return max(today, week_start) <= due_date < week_end
    return True


def answer_from_query_plan(
    plan: QueryPlan, snapshot: SyncSnapshot, *, today: date | None = None
) -> str | None:
    """Execute a plan against typed local records; return None for document queries."""

    if plan.intent == "courses":
        if not snapshot.courses:
            return "I could not find any courses in the latest Moodle snapshot."
        lines = [f"You are enrolled in {len(snapshot.courses)} courses:"]
        lines.extend(f"- {course.name}" for course in snapshot.courses)
        return "\n".join(lines)
    if plan.intent != "assignments":
        return None

    current_date = today or datetime.now().date()
    course_names = {course.id: course.name for course in snapshot.courses}
    assignments = [
        assignment
        for assignment in snapshot.assignments
        if _assignment_matches_time(assignment, plan, current_date)
    ]
    if plan.course_query:
        course_query = plan.course_query.casefold()
        assignments = [
            assignment
            for assignment in assignments
            if course_query in course_names.get(assignment.course_id, "").casefold()
        ]
    assignments.sort(key=lambda item: item.due_at or datetime.max.replace(tzinfo=UTC))
    if not assignments:
        return "I found no matching assignments in the latest Moodle snapshot."

    fields = frozenset(plan.fields) or frozenset({"due_date"})
    if plan.group_by == "course":
        grouped: dict[str, list[Assignment]] = {}
        for assignment in assignments:
            grouped.setdefault(course_names.get(assignment.course_id, "Unknown course"), []).append(
                assignment
            )
        lines = ["Assignments by course:"]
        for course_name, course_assignments in grouped.items():
            lines.append(f"\n{course_name}:")
            lines.extend(
                _format_assignment(item, course_name, fields, include_course=False)
                for item in course_assignments
            )
        return "\n".join(lines)
    return "Assignments:\n" + "\n".join(
        _format_assignment(item, course_names.get(item.course_id, "Unknown course"), fields)
        for item in assignments
    )
