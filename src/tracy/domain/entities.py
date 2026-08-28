from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Course:
    id: str
    name: str
    code: str | None = None
    credits: float | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    source_url: str | None = None
    category: str | None = None
    progress: float | None = None


@dataclass(frozen=True, slots=True)
class CourseSection:
    id: str
    course_id: str
    number: int
    title: str


@dataclass(frozen=True, slots=True)
class CourseModule:
    id: str
    course_id: str
    section_id: str
    name: str
    module_type: str
    source_url: str | None = None
    user_visible: bool = True
    restricted: bool = False


@dataclass(frozen=True, slots=True)
class Assignment:
    id: str
    course_id: str
    name: str
    due_at: datetime | None = None
    source_url: str | None = None
    opened_at: datetime | None = None
    cutoff_at: datetime | None = None
    description: str | None = None
    submission_status: str | None = None
    grading_status: str | None = None
    last_modified_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Document:
    id: str
    course_id: str
    name: str
    source_url: str
    content_hash: str
    local_path: Path | None = None
    content_type: str | None = None


@dataclass(frozen=True, slots=True)
class DocumentChunk:
    id: str
    document_id: str
    course_id: str
    course_name: str
    document_name: str
    source_url: str
    text: str
    page: int | None = None


@dataclass(frozen=True, slots=True)
class SyncSnapshot:
    synced_at: datetime
    courses: tuple[Course, ...] = ()
    sections: tuple[CourseSection, ...] = ()
    modules: tuple[CourseModule, ...] = ()
    assignments: tuple[Assignment, ...] = ()
    documents: tuple[Document, ...] = ()


@dataclass(frozen=True, slots=True)
class Citation:
    source_id: str
    label: str
    url: str | None = None
    page: int | None = None
