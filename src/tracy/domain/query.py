from dataclasses import dataclass
from typing import Literal

QueryIntent = Literal["assignments", "courses", "documents", "unsupported"]
QueryTimeRange = Literal["all", "this_week", "next_7_days", "upcoming", "overdue"]
QueryDirection = Literal["all", "upcoming", "past"]


@dataclass(frozen=True, slots=True)
class QueryPlan:
    """Validated interpretation of a natural-language Moodle question."""

    intent: QueryIntent
    time_range: QueryTimeRange = "all"
    direction: QueryDirection = "all"
    fields: tuple[str, ...] = ()
    group_by: str | None = None
    course_query: str | None = None
