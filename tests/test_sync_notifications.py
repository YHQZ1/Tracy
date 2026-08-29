from datetime import UTC, datetime

import pytest

from tracy.application import sync_moodle as sync_module
from tracy.config import Settings
from tracy.domain.entities import Course, SyncSnapshot


@pytest.mark.asyncio
async def test_sync_delivers_notifications_when_enabled(tmp_path, monkeypatch) -> None:
    snapshot = SyncSnapshot(
        synced_at=datetime(2026, 8, 29, tzinfo=UTC),
        courses=(Course(id="db", name="Databases"),),
    )
    notifications: list[tuple[str, object]] = []

    class FakeSource:
        async def sync(self) -> SyncSnapshot:
            return snapshot

    def fake_notify(data_dir, **kwargs) -> int:
        notifications.append((str(data_dir), kwargs))
        return 1

    monkeypatch.setattr(sync_module, "MoodleBrowserSource", lambda **_: FakeSource())
    monkeypatch.setattr(sync_module, "notify_reminders", fake_notify)

    await sync_module.sync_moodle(
        Settings(
            moodle_base_url="https://moodle.example",
            data_dir=tmp_path,
            moodle_profile_dir=tmp_path / "profile",
            moodle_headless=True,
            notifications_enabled=True,
            timezone="UTC",
        )
    )

    assert notifications == [(str(tmp_path), {"timezone": "UTC"})]
