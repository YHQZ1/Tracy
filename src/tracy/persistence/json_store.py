"""Small local JSON snapshot store for the first Tracy vertical slice."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from tracy.domain.entities import (
    Assignment,
    Course,
    CourseModule,
    CourseSection,
    Document,
    SyncSnapshot,
)


def _encode(value: Any) -> Any:
    if isinstance(value, datetime):
        return {"__type__": "datetime", "value": value.isoformat()}
    if isinstance(value, Path):
        return {"__type__": "path", "value": str(value)}
    if isinstance(value, tuple):
        return [_encode(item) for item in value]
    if isinstance(value, list):
        return [_encode(item) for item in value]
    if isinstance(value, dict):
        return {key: _encode(item) for key, item in value.items()}
    return value


def _decode(value: Any) -> Any:
    if isinstance(value, dict) and value.get("__type__") == "datetime":
        return datetime.fromisoformat(value["value"])
    if isinstance(value, dict) and value.get("__type__") == "path":
        return Path(value["value"])
    if isinstance(value, list):
        return [_decode(item) for item in value]
    if isinstance(value, dict):
        return {key: _decode(item) for key, item in value.items()}
    return value


class JsonSnapshotStore:
    """Persist one local, inspectable snapshot under Tracy's data directory."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.path = data_dir / "snapshot.json"

    def save(self, snapshot: SyncSnapshot) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        payload = _encode(asdict(snapshot))
        temporary_path = self.path.with_suffix(".json.tmp")
        temporary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary_path.replace(self.path)

    def load(self) -> SyncSnapshot:
        if not self.path.exists():
            raise FileNotFoundError(
                f"No Moodle snapshot found at {self.path}. Run `tracy sync` first."
            )
        payload = _decode(json.loads(self.path.read_text(encoding="utf-8")))
        return SyncSnapshot(
            synced_at=payload["synced_at"],
            courses=tuple(Course(**item) for item in payload.get("courses", [])),
            sections=tuple(CourseSection(**item) for item in payload.get("sections", [])),
            modules=tuple(CourseModule(**item) for item in payload.get("modules", [])),
            assignments=tuple(Assignment(**item) for item in payload.get("assignments", [])),
            documents=tuple(Document(**item) for item in payload.get("documents", [])),
        )
