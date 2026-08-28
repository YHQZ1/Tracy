"""Answer questions using structured Moodle data and indexed documents."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from tracy.domain.entities import Assignment, SyncSnapshot
from tracy.persistence.json_store import JsonSnapshotStore


def _format_assignment(assignment: Assignment) -> str:
    due = (
        assignment.due_at.strftime("%a, %d %b %Y at %I:%M %p")
        if assignment.due_at
        else "no due date"
    )
    citation = f" ([source]({assignment.source_url}))" if assignment.source_url else ""
    return f"- {assignment.name} — {due}{citation}"


def _this_week_bounds(today: date) -> tuple[datetime, datetime]:
    start = datetime.combine(today - timedelta(days=today.weekday()), datetime.min.time())
    return start, start + timedelta(days=7)


def _answer_from_snapshot(question: str, snapshot: SyncSnapshot) -> str:
    normalized = question.casefold()
    if "course" in normalized or "enrolled" in normalized:
        if not snapshot.courses:
            return "I could not find any courses in the latest Moodle snapshot."
        lines = [f"You are enrolled in {len(snapshot.courses)} courses:"]
        lines.extend(f"- {course.name}" for course in snapshot.courses)
        return "\n".join(lines)

    if "assignment" in normalized or "deadline" in normalized or "due" in normalized:
        assignments = list(snapshot.assignments)
        if "this week" in normalized:
            start, end = _this_week_bounds(datetime.now().date())
            assignments = [
                item
                for item in assignments
                if item.due_at and start <= item.due_at.replace(tzinfo=None) < end
            ]
        assignments.sort(
            key=lambda item: item.due_at or datetime.max.replace(tzinfo=UTC)
        )
        if not assignments:
            return "I found no matching assignments in the latest Moodle snapshot."
        return "Assignments:\n" + "\n".join(_format_assignment(item) for item in assignments)

    return (
        "The current Tracy slice can answer course-list and assignment-deadline questions. "
        "Run `tracy sync` first if the snapshot is out of date."
    )


async def answer_question(question: str, data_dir: Path) -> str:
    """Answer supported structured questions from the local snapshot."""

    snapshot = JsonSnapshotStore(data_dir).load()
    return _answer_from_snapshot(question, snapshot)
