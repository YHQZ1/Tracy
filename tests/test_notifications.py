from datetime import UTC, datetime

from tracy.application.notify_reminders import notify_reminders
from tracy.domain.entities import Assignment, Course, SyncSnapshot
from tracy.persistence.json_store import JsonSnapshotStore


class FakeNotificationSender:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def send(self, title: str, body: str) -> None:
        self.messages.append((title, body))


def _snapshot(*, due_at: datetime) -> SyncSnapshot:
    return SyncSnapshot(
        synced_at=datetime(2026, 8, 29, tzinfo=UTC),
        courses=(Course(id="db", name="Databases"),),
        assignments=(
            Assignment(
                id="pending",
                course_id="db",
                name="CA 1",
                due_at=due_at,
                submission_status="Not submitted",
            ),
            Assignment(
                id="submitted",
                course_id="db",
                name="Already submitted",
                due_at=due_at,
                submission_status="Submitted for grading",
            ),
        ),
    )


def test_notifications_are_sent_once_for_the_same_reminder(tmp_path) -> None:
    JsonSnapshotStore(tmp_path).save(
        _snapshot(due_at=datetime(2026, 8, 30, 12, tzinfo=UTC))
    )
    sender = FakeNotificationSender()

    first_count = notify_reminders(
        tmp_path,
        now=datetime(2026, 8, 29, 9, tzinfo=UTC),
        timezone="UTC",
        sender=sender,
    )
    second_count = notify_reminders(
        tmp_path,
        now=datetime(2026, 8, 29, 10, tzinfo=UTC),
        timezone="UTC",
        sender=sender,
    )

    assert first_count == 1
    assert second_count == 0
    assert len(sender.messages) == 1
    assert sender.messages[0][0] == "Tracy reminders"
    assert "CA 1 — Databases" in sender.messages[0][1]
    assert "Already submitted" not in sender.messages[0][1]


def test_changed_due_date_creates_a_new_reminder(tmp_path) -> None:
    store = JsonSnapshotStore(tmp_path)
    store.save(_snapshot(due_at=datetime(2026, 8, 30, 12, tzinfo=UTC)))
    sender = FakeNotificationSender()

    notify_reminders(
        tmp_path,
        now=datetime(2026, 8, 29, 9, tzinfo=UTC),
        timezone="UTC",
        sender=sender,
    )
    store.save(_snapshot(due_at=datetime(2026, 8, 31, 12, tzinfo=UTC)))

    count = notify_reminders(
        tmp_path,
        now=datetime(2026, 8, 29, 10, tzinfo=UTC),
        timezone="UTC",
        sender=sender,
    )

    assert count == 1
    assert len(sender.messages) == 2



def test_due_soon_reminder_is_followed_by_one_overdue_reminder(tmp_path) -> None:
    store = JsonSnapshotStore(tmp_path)
    store.save(_snapshot(due_at=datetime(2026, 8, 30, 12, tzinfo=UTC)))
    sender = FakeNotificationSender()

    first_count = notify_reminders(
        tmp_path,
        now=datetime(2026, 8, 29, 9, tzinfo=UTC),
        timezone="UTC",
        sender=sender,
    )
    second_count = notify_reminders(
        tmp_path,
        now=datetime(2026, 8, 31, 9, tzinfo=UTC),
        timezone="UTC",
        sender=sender,
    )

    assert first_count == 1
    assert second_count == 1
    assert "due soon" in sender.messages[0][1]
    assert "overdue" in sender.messages[1][1]
