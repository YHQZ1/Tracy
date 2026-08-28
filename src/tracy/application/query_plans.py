"""Heuristics and deterministic execution for validated Moodle query plans."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta

from tracy.domain.entities import Assignment, AttendanceSummary, Course, SyncSnapshot
from tracy.domain.query import QueryPlan
from tracy.domain.student import StudentContext

_COURSE_METADATA = {
    "april",
    "august",
    "december",
    "february",
    "january",
    "july",
    "june",
    "march",
    "may",
    "november",
    "october",
    "september",
    "sem",
    "semester",
}
_DEFAULT_ATTENDANCE_THRESHOLD = 75.0


def heuristic_query_plan(
    question: str, course_names: tuple[str, ...] = ()
) -> QueryPlan:
    """Provide an offline plan when the local planner is unavailable."""

    normalized = question.casefold()
    explicit_attendance = re.search(
        r"\b(?:attendance|attended|present|miss|missed|missing|absent|absence)\b",
        normalized,
    )
    attendance_projection = _attendance_projection(normalized)
    if explicit_attendance or attendance_projection:
        threshold = _attendance_threshold(normalized)
        if attendance_projection:
            return QueryPlan(
                intent="attendance",
                group_by="overall" if "overall" in normalized else None,
                course_query=infer_course_query(question, course_names),
                attendance_detail=attendance_projection,
                attendance_threshold=(
                    threshold if threshold is not None else _DEFAULT_ATTENDANCE_THRESHOLD
                ),
            )
        is_history = bool(
            re.search(
                r"\b(?:history|miss|missed|missing|absent|absence|classes|sessions)\b",
                normalized,
            )
        )
        is_absent = bool(re.search(r"\b(?:miss|missed|missing|absent|absence)\b", normalized))
        return QueryPlan(
            intent="attendance",
            group_by="overall" if "overall" in normalized else None,
            course_query=infer_course_query(question, course_names),
            attendance_detail="history" if is_history else "summary",
            attendance_status="absent" if is_absent else "all",
        )
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
            course_query=infer_course_query(question, course_names),
        )
    if "enrolled" in normalized or "list my courses" in normalized:
        return QueryPlan(intent="courses")
    return QueryPlan(intent="documents")


def _attendance_projection(normalized: str) -> str | None:
    """Recognize calculations and skip recommendations before the LLM is involved."""

    has_class_term = bool(
        re.search(r"\b(?:class|classes|lecture|lectures|session|sessions)\b", normalized)
    )
    if not has_class_term:
        return None
    if re.search(r"\bhow many\b.*\b(?:miss|skip|absen)\w*\b", normalized):
        return "max_misses"
    if re.search(
        r"\bhow many\b.*\b(?:attend|reach|get to|raise|improve|need)\w*\b", normalized
    ):
        return "required_sessions"
    if re.search(
        r"\b(?:can|could|should|safe|safest|afford)\b.*\b(?:miss|skip|absen)\w*\b",
        normalized,
    ) or re.search(r"\b(?:safest|afford to miss)\b", normalized):
        return "skip_suggestions"
    return None


def _attendance_threshold(normalized: str) -> float | None:
    match = re.search(r"\b(\d+(?:\.\d+)?)\s*%", normalized)
    if match:
        return float(match.group(1))
    match = re.search(
        r"\b(?:above|below|reach|get to|target(?:\s+of)?|at least)\s+"
        r"(\d+(?:\.\d+)?)\b",
        normalized,
    )
    if match and float(match.group(1)) <= 100:
        return float(match.group(1))
    return None


def _normalize_course_name(value: str) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", value.casefold()).split())


def _course_tokens(value: str) -> set[str]:
    return {
        token
        for token in _normalize_course_name(value).split()
        if not token.isdigit()
        and token not in _COURSE_METADATA
        and not set(token).issubset(set("ivxlcdm"))
    }


def infer_course_query(question: str, course_names: tuple[str, ...]) -> str | None:
    """Infer one course from words in a question without asking the LLM to guess."""

    question_tokens = set(_normalize_course_name(question).split())
    candidates = [
        course_name
        for course_name in course_names
        if _course_tokens(course_name).issubset(question_tokens)
    ]
    if not candidates:
        return None
    most_specific = max(len(_course_tokens(course_name)) for course_name in candidates)
    matches = [
        course_name
        for course_name in candidates
        if len(_course_tokens(course_name)) == most_specific
    ]
    return matches[0] if len(matches) == 1 else None


def resolve_course_id(course_query: str | None, courses: tuple[Course, ...]) -> str | None:
    """Resolve a natural-language course reference to one canonical Moodle course."""

    if not course_query:
        return None
    normalized_query = _normalize_course_name(course_query)
    if not normalized_query:
        return None

    exact_matches = [
        course for course in courses if _normalize_course_name(course.name) == normalized_query
    ]
    if len(exact_matches) == 1:
        return exact_matches[0].id

    query_tokens = set(normalized_query.split())
    candidates = [
        course
        for course in courses
        if query_tokens.issubset(set(_normalize_course_name(course.name).split()))
    ]
    return candidates[0].id if len(candidates) == 1 else None


def _normalize_batch_label(value: str) -> str:
    compact = re.sub(r"[^A-Z0-9]", "", value.upper())
    if compact.startswith("BATCH"):
        compact = compact[5:]
    if compact.startswith("LAB") and compact[3:].isdigit():
        return f"L{compact[3:]}"
    return compact


def _section_batch_label(title: str) -> str | None:
    normalized = title.casefold()
    match = re.search(r"\b(?:batch|group)\s*[-:]?\s*([a-z]\s*\d+)\b", normalized)
    if match:
        return _normalize_batch_label(match.group(1))
    match = re.search(r"\blab\s*[-:]?\s*(\d+)\b", normalized)
    if match:
        return _normalize_batch_label(f"L{match.group(1)}")
    match = re.fullmatch(r"\s*([a-z]\s*\d+)\s*", normalized)
    return _normalize_batch_label(match.group(1)) if match else None


def _assignment_batch_labels(snapshot: SyncSnapshot) -> dict[str, str | None]:
    sections = {section.id: section for section in snapshot.sections}
    return {
        module.id: _section_batch_label(sections[module.section_id].title)
        if module.section_id in sections
        else None
        for module in snapshot.modules
        if module.module_type == "assign"
    }


def _scope_assignments(
    assignments: list[Assignment], snapshot: SyncSnapshot, context: StudentContext
) -> list[Assignment]:
    """Select matching batch activities, falling back to general activities by name."""

    configured_batches = {
        item.course_id: _normalize_batch_label(item.batch) for item in context.lab_batches
    }
    batch_labels = _assignment_batch_labels(snapshot)
    grouped: dict[tuple[str, str], list[Assignment]] = {}
    for assignment in assignments:
        key = (assignment.course_id, _normalize_course_name(assignment.name))
        grouped.setdefault(key, []).append(assignment)

    selected: list[Assignment] = []
    for group in grouped.values():
        explicit = [item for item in group if batch_labels.get(item.id)]
        if not explicit:
            selected.extend(group)
            continue
        configured_batch = configured_batches.get(group[0].course_id)
        matching = [
            item
            for item in explicit
            if batch_labels.get(item.id) == configured_batch
        ]
        selected.extend(matching or [item for item in group if not batch_labels.get(item.id)])
    return selected


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


def _attendance_status_matches(status: str, requested: str) -> bool:
    normalized = status.casefold()
    if requested == "absent":
        return "absent" in normalized or normalized in {"a", "ab"}
    if requested == "present":
        return "present" in normalized or normalized == "p"
    if requested == "late":
        return "late" in normalized or normalized == "l"
    if requested == "excused":
        return "excused" in normalized or normalized == "e"
    return True


def _attendance_percentage(attended: int, total: int) -> float:
    return attended / total * 100 if total else 0.0


def _max_additional_absences(attended: int, total: int, threshold: float) -> int:
    if total == 0 or _attendance_percentage(attended, total) <= threshold:
        return 0
    if threshold <= 0:
        return 0
    misses = 0
    while _attendance_percentage(attended, total + misses + 1) > threshold:
        misses += 1
    return misses


def _required_sessions(attended: int, total: int, threshold: float) -> int | None:
    if total == 0 or _attendance_percentage(attended, total) >= threshold:
        return 0
    if threshold >= 100:
        return None
    sessions = 0
    while _attendance_percentage(attended + sessions, total + sessions) < threshold:
        sessions += 1
    return sessions


def _source_line(summaries: list[AttendanceSummary]) -> str:
    source_urls = sorted({item.source_url for item in summaries if item.source_url})
    return f"\nsource: {source_urls[0]}" if source_urls else ""


def _attendance_summaries_for_plan(
    plan: QueryPlan, snapshot: SyncSnapshot
) -> tuple[list[AttendanceSummary], str | None]:
    summaries = list(snapshot.attendance)
    if not plan.course_query:
        return summaries, None
    course_id = resolve_course_id(plan.course_query, snapshot.courses)
    if course_id is None:
        return [], (
            "I could not identify a unique Moodle course matching "
            f"{plan.course_query!r}."
        )
    return [item for item in summaries if item.course_id == course_id], None


def answer_from_query_plan(
    plan: QueryPlan,
    snapshot: SyncSnapshot,
    *,
    today: date | None = None,
    student_context: StudentContext | None = None,
) -> str | None:
    """Execute a plan against typed local records; return None for document queries."""

    if plan.intent == "courses":
        if not snapshot.courses:
            return "I could not find any courses in the latest Moodle snapshot."
        lines = [f"You are enrolled in {len(snapshot.courses)} courses:"]
        lines.extend(f"- {course.name}" for course in snapshot.courses)
        return "\n".join(lines)
    if plan.intent == "attendance":
        if plan.attendance_detail == "history":
            records = list(snapshot.attendance_records)
            if plan.course_query:
                course_id = resolve_course_id(plan.course_query, snapshot.courses)
                if course_id is None:
                    return (
                        "I could not identify a unique Moodle course matching "
                        f"{plan.course_query!r}."
                    )
                records = [item for item in records if item.course_id == course_id]
            if plan.attendance_status != "all":
                records = [
                    item
                    for item in records
                    if _attendance_status_matches(item.status, plan.attendance_status)
                ]
            if not records:
                if not snapshot.attendance_records:
                    return (
                        "I could not find individual attendance history in the latest "
                        "Moodle snapshot."
                    )
                return "I found no matching attendance history in the latest Moodle snapshot."
            records.sort(key=lambda item: item.session_at)
            lines = ["Attendance history:"]
            for record in records:
                session = record.session_at.strftime("%a, %d %b %Y at %I:%M %p")
                details = [
                    session,
                    record.course_name,
                    record.status,
                    record.attendance_module_name,
                ]
                if record.description:
                    details.append(record.description)
                lines.append(f"- {' — '.join(details)}")
                if record.remarks:
                    lines.append(f"  remarks: {record.remarks}")
                if record.source_url:
                    lines.append(f"  source: {record.source_url}")
            return "\n".join(lines)
        summaries, course_error = _attendance_summaries_for_plan(plan, snapshot)
        if course_error:
            return course_error
        if not summaries:
            return "I could not find attendance data in the latest Moodle snapshot."
        threshold = (
            plan.attendance_threshold
            if plan.attendance_threshold is not None
            else _DEFAULT_ATTENDANCE_THRESHOLD
        )
        total_sessions = sum(item.total_sessions for item in summaries)
        attended_sessions = sum(item.attended_sessions for item in summaries)
        if plan.attendance_detail == "max_misses":
            current_percentage = _attendance_percentage(attended_sessions, total_sessions)
            safe_misses = _max_additional_absences(
                attended_sessions, total_sessions, threshold
            )
            scope = (
                "overall attendance"
                if not plan.course_query
                else f"{summaries[0].course_name} attendance"
            )
            if safe_misses == 0 and current_percentage <= threshold:
                answer = (
                    f"Current {scope} attendance is {attended_sessions}/{total_sessions} "
                    f"({current_percentage:.2f}%), which is at or below {threshold:.2f}%. "
                    "No additional absences are safe."
                )
            else:
                safe_percentage = _attendance_percentage(
                    attended_sessions, total_sessions + safe_misses
                )
                next_percentage = _attendance_percentage(
                    attended_sessions, total_sessions + safe_misses + 1
                )
                answer = (
                    f"You can miss up to {safe_misses} more classes in {scope} and stay "
                    f"above {threshold:.2f}%. Current: {attended_sessions}/{total_sessions} "
                    f"({current_percentage:.2f}%). After {safe_misses}: "
                    f"{attended_sessions}/{total_sessions + safe_misses} "
                    f"({safe_percentage:.2f}%). After {safe_misses + 1}: "
                    f"{attended_sessions}/{total_sessions + safe_misses + 1} "
                    f"({next_percentage:.2f}%)."
                )
            return f"{answer}{_source_line(summaries)}"
        if plan.attendance_detail == "required_sessions":
            current_percentage = _attendance_percentage(attended_sessions, total_sessions)
            needed = _required_sessions(attended_sessions, total_sessions, threshold)
            scope = (
                "overall attendance"
                if not plan.course_query
                else f"{summaries[0].course_name} attendance"
            )
            if needed is None:
                answer = (
                    f"It is not possible to reach exactly {threshold:.2f}% in {scope} "
                    "by only attending future classes."
                )
            elif needed == 0:
                answer = (
                    f"You already meet the {threshold:.2f}% target in {scope}: "
                    f"{attended_sessions}/{total_sessions} ({current_percentage:.2f}%)."
                )
            else:
                final_percentage = _attendance_percentage(
                    attended_sessions + needed, total_sessions + needed
                )
                answer = (
                    f"You need to attend the next {needed} classes in {scope} to reach "
                    f"{threshold:.2f}%: {attended_sessions + needed}/"
                    f"{total_sessions + needed} ({final_percentage:.2f}%)."
                )
            return f"{answer}{_source_line(summaries)}"
        if plan.attendance_detail == "skip_suggestions":
            safe: list[tuple[float, AttendanceSummary, int]] = []
            unsafe: list[tuple[float, AttendanceSummary]] = []
            for summary in summaries:
                if summary.total_sessions == 0:
                    continue
                percentage = _attendance_percentage(
                    summary.attended_sessions, summary.total_sessions
                )
                misses = _max_additional_absences(
                    summary.attended_sessions, summary.total_sessions, threshold
                )
                if misses:
                    safe.append((percentage, summary, misses))
                else:
                    unsafe.append((percentage, summary))
            safe.sort(key=lambda item: (-item[0], item[1].course_name))
            unsafe.sort(key=lambda item: (item[0], item[1].course_name))
            overall_misses = _max_additional_absences(
                attended_sessions, total_sessions, threshold
            )
            lines = [
                f"Overall headroom: up to {overall_misses} more absences while staying "
                f"above {threshold:.2f}%.",
                f"Safest courses by individual {threshold:.2f}% buffer:",
            ]
            if safe:
                for percentage, summary, misses in safe:
                    after_percentage = _attendance_percentage(
                        summary.attended_sessions,
                        summary.total_sessions + misses,
                    )
                    lines.append(
                        f"- {summary.course_name} — {summary.attended_sessions}/"
                        f"{summary.total_sessions} ({percentage:.2f}%); can miss {misses} "
                        f"more and remain at {after_percentage:.2f}%"
                    )
            else:
                lines.append("- None of the courses currently has safe absence headroom.")
            if unsafe:
                lines.append(f"Already at or below {threshold:.2f}%; avoid more absences:")
                for percentage, summary in unsafe:
                    lines.append(
                        f"- {summary.course_name} — {summary.attended_sessions}/"
                        f"{summary.total_sessions} ({percentage:.2f}%)"
                    )
            return "\n".join(lines) + _source_line(summaries)
        if plan.group_by == "overall":
            if total_sessions == 0:
                return "I could not calculate overall attendance from the latest Moodle snapshot."
            percentage = attended_sessions / total_sessions * 100
            answer = (
                f"Overall attendance: {attended_sessions}/{total_sessions} "
                f"total sessions attended ({percentage:.2f}%)"
            )
            source_urls = sorted(
                {item.source_url for item in summaries if item.source_url}
            )
            return f"{answer}\nsource: {source_urls[0]}" if source_urls else answer
        lines = ["Attendance:"]
        for summary in summaries:
            percentage = (
                f"{summary.percentage:.2f}%"
                if summary.percentage is not None
                else "percentage unavailable"
            )
            lines.append(
                f"- {summary.course_name} — {summary.attended_sessions}/"
                f"{summary.total_sessions} attended, "
                f"{summary.marked_sessions} marked ({percentage})"
            )
            if summary.source_url:
                lines.append(f"  source: {summary.source_url}")
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
        course_id = resolve_course_id(plan.course_query, snapshot.courses)
        if course_id is None:
            return f"I could not identify a unique Moodle course matching {plan.course_query!r}."
        assignments = [
            assignment
            for assignment in assignments
            if assignment.course_id == course_id
        ]
    if student_context is not None:
        assignments = _scope_assignments(assignments, snapshot, student_context)
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
