from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Course:
    id: str
    name: str
    code: str | None = None
    credits: float | None = None


@dataclass(frozen=True, slots=True)
class Assignment:
    id: str
    course_id: str
    name: str
    due_at: datetime | None = None
    source_url: str | None = None


@dataclass(frozen=True, slots=True)
class Document:
    id: str
    course_id: str
    name: str
    source_url: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class Citation:
    source_id: str
    label: str
    url: str | None = None
    page: int | None = None
