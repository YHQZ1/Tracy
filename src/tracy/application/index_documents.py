"""Application use case for building the local document index."""

from pathlib import Path

from tracy.adapters.documents.index import DocumentIndex, build_document_index
from tracy.persistence.json_store import JsonSnapshotStore


def index_documents(data_dir: Path) -> DocumentIndex:
    """Build an index from the latest Moodle snapshot."""

    snapshot = JsonSnapshotStore(data_dir).load()
    return build_document_index(snapshot, data_dir)
