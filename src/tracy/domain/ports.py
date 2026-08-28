from typing import Protocol

from tracy.domain.entities import SyncSnapshot


class MoodleSource(Protocol):
    """Interface for reading the authenticated student's Moodle data."""

    async def sync(self) -> SyncSnapshot: ...
