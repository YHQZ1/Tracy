from datetime import UTC, datetime
from pathlib import Path

import pytest

from tracy.adapters.documents.index import (
    DocumentIndex,
    JsonDocumentIndexStore,
    build_document_index,
)
from tracy.application.answer_question import answer_question
from tracy.domain.entities import Course, Document, DocumentChunk, SyncSnapshot
from tracy.persistence.json_store import JsonSnapshotStore


class RecordingComposer:
    def __init__(self) -> None:
        self.question = ""
        self.context = ""

    async def compose(self, question: str, context: str) -> str:
        self.question = question
        self.context = context
        return "Compiler Construction is a 3-credit course. [1]"


@pytest.mark.asyncio
async def test_document_index_returns_course_scoped_citation(tmp_path: Path) -> None:
    document_path = tmp_path / "compiler-notes.txt"
    document_path.write_text("Lexical analysis creates tokens for the compiler.", encoding="utf-8")
    snapshot = SyncSnapshot(
        synced_at=datetime.now(UTC),
        courses=(Course(id="1", name="Compiler Construction"),),
        documents=(
            Document(
                id="doc-1",
                course_id="1",
                name="Compiler Notes",
                source_url="https://moodle.example/pluginfile.php/compiler-notes.txt",
                content_hash="hash",
                local_path=document_path,
                content_type="text/plain",
            ),
        ),
    )

    JsonSnapshotStore(tmp_path).save(snapshot)
    index = build_document_index(snapshot, tmp_path)
    answer = await answer_question("Which document covers compiler tokens?", tmp_path)

    assert len(index.chunks) == 1
    assert "Compiler Notes" in answer
    assert "Compiler Construction" in answer
    assert "Lexical analysis creates tokens" in answer
    assert "compiler-notes.txt" in answer


@pytest.mark.asyncio
async def test_document_search_prioritizes_requested_unit_and_syllabus(tmp_path: Path) -> None:
    JsonSnapshotStore(tmp_path).save(
        SyncSnapshot(
            synced_at=datetime.now(UTC),
            courses=(Course(id="1", name="Compiler Construction"),),
        )
    )
    JsonDocumentIndexStore(tmp_path).save(
        DocumentIndex(
            (
                DocumentChunk(
                    id="unit-i",
                    document_id="i",
                    course_id="1",
                    course_name="Compiler Construction",
                    document_name="Compiler_Construction_Unit_I.pptx",
                    source_url="https://moodle.example/unit-i",
                    text="Compiler Construction Unit I",
                    page=1,
                ),
                DocumentChunk(
                    id="unit-ii",
                    document_id="ii",
                    course_id="1",
                    course_name="Compiler Construction",
                    document_name="Compiler_Construction_Unit_II.pptx",
                    source_url="https://moodle.example/unit-ii",
                    text="Compiler Construction Unit II Role of a Parser",
                    page=1,
                ),
                DocumentChunk(
                    id="syllabus",
                    document_id="syllabus",
                    course_id="1",
                    course_name="Compiler Construction",
                    document_name="TE7751_Compiler_Construction.pdf",
                    source_url="https://moodle.example/syllabus",
                    text="Course Outline: Learning Objectives, Hours, Evaluation, and Pedagogy",
                    page=1,
                ),
                DocumentChunk(
                    id="lab-syllabus",
                    document_id="lab-syllabus",
                    course_id="1",
                    course_name="Compiler Construction Lab",
                    document_name="T7478_Compiler_Construction_Lab.pdf",
                    source_url="https://moodle.example/lab-syllabus",
                    text="Course Outline: Learning Objectives, Hours, Evaluation, and Pedagogy",
                    page=1,
                ),
                DocumentChunk(
                    id="hci-syllabus",
                    document_id="hci-syllabus",
                    course_id="2",
                    course_name="Human Computer Interface",
                    document_name="Syllabus_1_.pdf",
                    source_url="https://moodle.example/hci-syllabus",
                    text="Course Outline: Learning Objectives, Hours, Evaluation, and Pedagogy",
                    page=1,
                ),
            )
        )
    )

    unit_answer = await answer_question("what is the unit 2 of compiler construction?", tmp_path)
    syllabus_answer = await answer_question(
        "what is the syllabus of compiler construction?", tmp_path
    )

    assert "Compiler_Construction_Unit_II.pptx" in unit_answer.splitlines()[1]
    assert "TE7751_Compiler_Construction.pdf" in syllabus_answer.splitlines()[1]
    assert "Syllabus_1_.pdf" not in syllabus_answer


@pytest.mark.asyncio
async def test_document_question_uses_composer_with_cited_context(tmp_path: Path) -> None:
    JsonSnapshotStore(tmp_path).save(
        SyncSnapshot(
            synced_at=datetime.now(UTC),
            courses=(Course(id="1", name="Compiler Construction"),),
        )
    )
    JsonDocumentIndexStore(tmp_path).save(
        DocumentIndex(
            (
                DocumentChunk(
                    id="syllabus",
                    document_id="syllabus",
                    course_id="1",
                    course_name="Compiler Construction",
                    document_name="Compiler Syllabus",
                    source_url="https://moodle.example/compiler-syllabus",
                    text="Compiler Construction Course Credit: 3.",
                    page=2,
                ),
            )
        )
    )
    composer = RecordingComposer()

    answer = await answer_question(
        "What is the credit value of Compiler Construction?", tmp_path, composer=composer
    )

    assert answer == "Compiler Construction is a 3-credit course. [1]"
    assert "Compiler Syllabus" in composer.context
    assert "page/slide 2" in composer.context
    assert "https://moodle.example/compiler-syllabus" in composer.context
