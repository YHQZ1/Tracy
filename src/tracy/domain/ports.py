from collections.abc import Sequence
from typing import Protocol

from tracy.domain.entities import Assignment, Course


class MoodleSource(Protocol):
    """Interface for reading the authenticated student's Moodle data."""

    async def courses(self) -> Sequence[Course]: ...

    async def assignments(self, course_id: str | None = None) -> Sequence[Assignment]: ...
