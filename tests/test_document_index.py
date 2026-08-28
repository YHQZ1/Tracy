from datetime import UTC, datetime
from pathlib import Path

import pytest

from tracy.adapters.documents.index import build_document_index
from tracy.application.answer_question import answer_question
from tracy.domain.entities import Course, Document, SyncSnapshot
from tracy.persistence.json_store import JsonSnapshotStore


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
