"""Deliver deduplicated assignment reminders from the local snapshot."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo

from tracy.adapters.notifications.macos import MacOSNotificationSender
from tracy.application.create_reminders import _needs_action
from tracy.application.query_plans import _scope_assignments
from tracy.domain.entities import Assignment, SyncSnapshot
from tracy.domain.student import StudentContext
from tracy.persistence.json_store import JsonSnapshotStore
from tracy.persistence.student_context_store import JsonStudentContextStore

_STATE_FILENAME = "notification-state.json"


class NotificationSender(Protocol):
    def send(self, title: str, body: str) -> None: ...


@dataclass(frozen=True, slots=True)
class _ReminderCandidate:
    assignment: Assignment
    course_name: str
    category: str

    @property
    def key(self) -> str:
        due_at = self.assignment.due_at.isoformat() if self.assignment.due_at else "none"
        cutoff_at = self.assignment.cutoff_at.isoformat() if self.assignment.cutoff_at else "none"
        return f"{self.assignment.id}|{self.category}|{due_at}|{cutoff_at}"


def _in_timezone(value: datetime, timezone: ZoneInfo) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone)
    return value.astimezone(timezone)


def _format_datetime(value: datetime, timezone: ZoneInfo) -> str:
    return _in_timezone(value, timezone).strftime("%a, %d %b %Y at %I:%M %p")


def _load_state(data_dir: Path) -> set[str]:
    path = data_dir / _STATE_FILENAME
    if not path.exists():
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    return set(payload.get("sent_keys", []))


def _save_state(data_dir: Path, sent_keys: set[str]) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / _STATE_FILENAME
    temporary_path = path.with_suffix(".json.tmp")
    temporary_path.write_text(
        json.dumps({"sent_keys": sorted(sent_keys)}, indent=2),
        encoding="utf-8",
    )
    temporary_path.replace(path)


def _candidates(
    snapshot: SyncSnapshot,
    student_context: StudentContext | None,
    *,
    now: datetime,
    timezone: ZoneInfo,
    window_days: int,
) -> list[_ReminderCandidate]:
    assignments = list(snapshot.assignments)
    if student_context is not None:
        assignments = _scope_assignments(assignments, snapshot, student_context)
    course_names = {course.id: course.name for course in snapshot.courses}
    current = _in_timezone(now, timezone)
    window_end = current.timestamp() + window_days * 24 * 60 * 60
    candidates: list[_ReminderCandidate] = []
    for assignment in assignments:
        if not _needs_action(assignment) or assignment.due_at is None:
            continue
        due_at = _in_timezone(assignment.due_at, timezone)
        if due_at < current:
            category = "overdue"
        elif due_at.timestamp() < window_end:
            category = "due soon"
        else:
            continue
        candidates.append(
            _ReminderCandidate(
                assignment=assignment,
                course_name=course_names.get(assignment.course_id, "Unknown course"),
                category=category,
            )
        )
    return sorted(
        candidates,
        key=lambda item: _in_timezone(item.assignment.due_at, timezone),
    )


def _format_body(candidates: list[_ReminderCandidate], timezone: ZoneInfo) -> str:
    count = len(candidates)
    assignment_label = "assignment" if count == 1 else "assignments"
    lines = [f"{count} {assignment_label} need your attention:"]
    for candidate in candidates:
        assignment = candidate.assignment
        lines.append(
            f"- {assignment.name} — {candidate.course_name} "
            f"({candidate.category}; due {_format_datetime(assignment.due_at, timezone)})"
        )
    return "\n".join(lines)


def notify_reminders(
    data_dir: Path,
    *,
    now: datetime | None = None,
    timezone: str = "Asia/Kolkata",
    window_days: int = 7,
    sender: NotificationSender | None = None,
) -> int:
    """Send one notification for newly actionable reminders and return its count."""

    if window_days <= 0:
        raise ValueError("Reminder window must be greater than zero days.")
    local_timezone = ZoneInfo(timezone)
    snapshot = JsonSnapshotStore(data_dir).load()
    try:
        student_context = JsonStudentContextStore(data_dir).load()
    except FileNotFoundError:
        student_context = None
    current = now or datetime.now(local_timezone)
    sent_keys = _load_state(data_dir)
    pending = [
        candidate
        for candidate in _candidates(
            snapshot,
            student_context,
            now=current,
            timezone=local_timezone,
            window_days=window_days,
        )
        if candidate.key not in sent_keys
    ]
    if not pending:
        return 0
    active_sender = sender or MacOSNotificationSender()
    active_sender.send("Tracy reminders", _format_body(pending, local_timezone))
    _save_state(data_dir, sent_keys | {candidate.key for candidate in pending})
    return 1
