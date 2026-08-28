"""Local Ollama query-planning adapter."""

from __future__ import annotations

import json
from typing import Any

import httpx

from tracy.domain.query import QueryPlan

_SYSTEM_PROMPT = (
    "You are Tracy's query planner. Translate a student's Moodle question into exactly one "
    "JSON object. Never answer the question and never invent Moodle facts. Use intent "
    "assignments for assignment/deadline/submission questions, courses for enrollment/list "
    "questions, attendance for attendance questions, documents for "
    "syllabus/material/announcement questions, and unsupported "
    "only when none applies. time_range must be all, this_week, next_7_days, upcoming, or "
    "overdue. direction must be all, upcoming, or past. fields may contain name, due_date, "
    "cutoff_date, and submission_status. group_by may be course, overall, or null. For "
    "attendance, attendance_detail must be summary or history and attendance_status must "
    "be all, absent, present, late, or excused. Return "
    "course_query must be null when no course is named; otherwise copy the closest matching "
    "course name from the known Moodle courses. Return JSON only."
)
_VALID_INTENTS = {"assignments", "courses", "documents", "attendance", "unsupported"}
_VALID_TIME_RANGES = {"all", "this_week", "next_7_days", "upcoming", "overdue"}
_VALID_DIRECTIONS = {"all", "upcoming", "past"}
_VALID_FIELDS = {"name", "due_date", "cutoff_date", "submission_status"}


def _validated_plan(payload: Any) -> QueryPlan:
    if not isinstance(payload, dict):
        raise RuntimeError("Ollama returned an invalid query plan.")

    intent = payload.get("intent")
    time_range = payload.get("time_range", "all")
    direction = payload.get("direction", "all")
    group_by = payload.get("group_by")
    fields = payload.get("fields", [])
    attendance_detail = payload.get("attendance_detail", "summary")
    attendance_status = payload.get("attendance_status", "all")
    if intent not in _VALID_INTENTS:
        raise RuntimeError("Ollama returned an unknown query intent.")
    if time_range not in _VALID_TIME_RANGES or direction not in _VALID_DIRECTIONS:
        raise RuntimeError("Ollama returned an invalid query time range.")
    if group_by not in {None, "course", "overall"}:
        raise RuntimeError("Ollama returned an invalid grouping.")
    if attendance_detail not in {"summary", "history"}:
        raise RuntimeError("Ollama returned an invalid attendance detail.")
    if attendance_status not in {"all", "absent", "present", "late", "excused"}:
        raise RuntimeError("Ollama returned an invalid attendance status.")
    if not isinstance(fields, list) or any(field not in _VALID_FIELDS for field in fields):
        raise RuntimeError("Ollama returned invalid query fields.")

    course_query = payload.get("course_query")
    if course_query is not None and not isinstance(course_query, str):
        raise RuntimeError("Ollama returned an invalid course filter.")
    course_query = (
        course_query.strip() or None if course_query is not None else None
    )
    return QueryPlan(
        intent=intent,
        time_range=time_range,
        direction=direction,
        fields=tuple(fields),
        group_by=group_by,
        course_query=course_query,
        attendance_detail=attendance_detail,
        attendance_status=attendance_status,
    )


class OllamaQuestionPlanner:
    """Translate natural-language questions into validated local query plans."""

    def __init__(
        self,
        model: str = "gemma3:4b",
        base_url: str = "http://localhost:11434",
        client: Any | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._client = client
        self._timeout = timeout

    async def plan(
        self, question: str, course_names: tuple[str, ...] = ()
    ) -> QueryPlan:
        known_courses = "\n".join(f"- {name}" for name in course_names) or "(not provided)"
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Known Moodle courses:\n{known_courses}\n\nQuestion: {question}",
                },
            ],
            "format": "json",
            "stream": False,
        }
        try:
            if self._client is None:
                async with httpx.AsyncClient(
                    base_url=self._base_url, timeout=self._timeout
                ) as client:
                    response = await client.post("/api/chat", json=payload)
            else:
                response = await self._client.post("/api/chat", json=payload)
            response.raise_for_status()
            body = response.json()
            content = body.get("message", {}).get("content", "")
            return _validated_plan(json.loads(content))
        except httpx.ConnectError as error:
            raise RuntimeError(
                f"Could not connect to Ollama at {self._base_url}. Start Ollama and try again."
            ) from error
        except httpx.HTTPError as error:
            raise RuntimeError(f"Ollama planner request failed: {error}") from error
        except (json.JSONDecodeError, AttributeError, TypeError, ValueError) as error:
            raise RuntimeError("Ollama returned an invalid JSON query plan.") from error
