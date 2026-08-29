"""Synchronize Moodle data into Tracy's canonical representation."""

import logging

from tracy.adapters.moodle.browser import MoodleBrowserSource
from tracy.adapters.notifications.macos import NotificationDeliveryError
from tracy.application.notify_reminders import notify_reminders
from tracy.config import Settings
from tracy.domain.entities import SyncSnapshot
from tracy.persistence.json_store import JsonSnapshotStore

logger = logging.getLogger(__name__)


async def sync_moodle(settings: Settings) -> SyncSnapshot:
    """Sync accessible Moodle data and persist a local snapshot."""

    if not settings.moodle_base_url:
        raise ValueError(
            "TRACY_MOODLE_BASE_URL is required. Copy your Moodle site URL into `.env`."
        )

    source = MoodleBrowserSource(
        base_url=settings.moodle_base_url,
        profile_dir=settings.moodle_profile_dir,
        data_dir=settings.data_dir,
        headless=settings.moodle_headless,
        timezone=settings.timezone,
    )
    snapshot = await source.sync()
    JsonSnapshotStore(settings.data_dir).save(snapshot)
    if settings.notifications_enabled:
        try:
            notify_reminders(settings.data_dir, timezone=settings.timezone)
        except NotificationDeliveryError as error:
            logger.warning("Could not deliver Tracy reminders: %s", error)
    return snapshot
