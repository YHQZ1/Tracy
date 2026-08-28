"""Build deterministic reminders from trusted Moodle assignment dates."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from tracy.application.query_plans import _scope_assignments
from tracy.domain.entities import Assignment, SyncSnapshot
from tracy.domain.student import StudentContext
from tracy.persistence.json_store import JsonSnapshotStore
from tracy.persistence.student_context_store import JsonStudentContextStore


def _in_timezone(value: datetime, timezone: ZoneInfo) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone)
    return value.astimezone(timezone)


def _format_datetime(value: datetime, timezone: ZoneInfo) -> str:
    return _in_timezone(value, timezone).strftime("%a, %d %b %Y at %I:%M %p")


def _needs_action(assignment: Assignment) -> bool:
    """Keep submitted, graded, and returned activities out of reminders."""

    status = (assignment.submission_status or "").casefold()
    if re.search(r"\b(?:not submitted|no submissions|draft|not attempted)\b", status):
        return True
    return not re.search(r"\b(?:submitted|graded|returned|completed|complete)\b", status)


def _format_reminder(assignment: Assignment, course_name: str, timezone: ZoneInfo) -> str:
    parts = [
        f"- {assignment.name} — {course_name}",
        f"due {_format_datetime(assignment.due_at, timezone)}",
    ]
    if assignment.cutoff_at:
        parts.append(f"cutoff: {_format_datetime(assignment.cutoff_at, timezone)}")
    parts.append(f"status: {assignment.submission_status or 'not available'}")
    if assignment.source_url:
        parts.append(f"source: [link={assignment.source_url}]Open in Moodle[/link]")
    return " — ".join(parts)


def _count_label(count: int, singular: str, plural: str) -> str:
    return singular if count == 1 else plural


def _build_report(
    snapshot: SyncSnapshot,
    student_context: StudentContext | None,
    *,
    now: datetime,
    timezone: ZoneInfo,
    window_days: int,
) -> str:
    assignments = list(snapshot.assignments)
    if student_context is not None:
        assignments = _scope_assignments(assignments, snapshot, student_context)
    course_names = {course.id: course.name for course in snapshot.courses}
    current = _in_timezone(now, timezone)
    window_end = current.timestamp() + window_days * 24 * 60 * 60
    overdue: list[Assignment] = []
    upcoming: list[Assignment] = []
    undated_count = 0
    for assignment in assignments:
        if not _needs_action(assignment):
            continue
        if assignment.due_at is None:
            undated_count += 1
            continue
        due_at = _in_timezone(assignment.due_at, timezone)
        if due_at < current:
            overdue.append(assignment)
        elif due_at.timestamp() < window_end:
            upcoming.append(assignment)

    overdue.sort(key=lambda item: _in_timezone(item.due_at, timezone))
    upcoming.sort(key=lambda item: _in_timezone(item.due_at, timezone))
    lines = ["Reminders:"]
    if overdue:
        lines.append("\nOverdue assignments:")
        lines.extend(
            _format_reminder(item, course_names.get(item.course_id, "Unknown course"), timezone)
            for item in overdue
        )
    if upcoming:
        lines.append(f"\nDue in the next {window_days} days:")
        lines.extend(
            _format_reminder(item, course_names.get(item.course_id, "Unknown course"), timezone)
            for item in upcoming
        )
    if not overdue and not upcoming:
        lines.append(f"No assignments are overdue or due in the next {window_days} days.")
    if undated_count:
        assignment_label = _count_label(undated_count, "assignment has", "assignments have")
        lines.append(
            f"\n{undated_count} {assignment_label} no due date and was not included above."
        )
    return "\n".join(lines)


async def create_reminders(
    data_dir: Path,
    *,
    now: datetime | None = None,
    timezone: str = "Asia/Kolkata",
    window_days: int = 7,
) -> str:
    """Return overdue and near-term actionable reminders from the local snapshot."""

    if window_days <= 0:
        raise ValueError("Reminder window must be greater than zero days.")
    local_timezone = ZoneInfo(timezone)
    snapshot = JsonSnapshotStore(data_dir).load()
    try:
        student_context = JsonStudentContextStore(data_dir).load()
    except FileNotFoundError:
        student_context = None
    current = now or datetime.now(local_timezone)
    return _build_report(
        snapshot,
        student_context,
        now=current,
        timezone=local_timezone,
        window_days=window_days,
    )
