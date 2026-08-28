from dataclasses import dataclass
from typing import Literal

QueryIntent = Literal["assignments", "courses", "documents", "attendance", "unsupported"]
QueryTimeRange = Literal["all", "this_week", "next_7_days", "upcoming", "overdue"]
QueryDirection = Literal["all", "upcoming", "past"]
AttendanceDetail = Literal[
    "summary", "history", "max_misses", "required_sessions", "skip_suggestions"
]
AttendanceStatus = Literal["all", "absent", "present", "late", "excused"]


@dataclass(frozen=True, slots=True)
class QueryPlan:
    """Validated interpretation of a natural-language Moodle question."""

    intent: QueryIntent
    time_range: QueryTimeRange = "all"
    direction: QueryDirection = "all"
    fields: tuple[str, ...] = ()
    group_by: str | None = None
    course_query: str | None = None
    attendance_detail: AttendanceDetail = "summary"
    attendance_status: AttendanceStatus = "all"
    attendance_threshold: float | None = None
