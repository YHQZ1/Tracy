"""Local persistence for one student context."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from tracy.domain.student import LabBatch, StudentContext


class JsonStudentContextStore:
    """Persist student context separately from the Moodle snapshot."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.path = data_dir / "student-context.json"

    def save(self, context: StudentContext) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        payload = asdict(context)
        temporary_path = self.path.with_suffix(".json.tmp")
        temporary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary_path.replace(self.path)

    def load(self) -> StudentContext:
        if not self.path.exists():
            raise FileNotFoundError(
                f"No student context found at {self.path}. Run `tracy setup` first."
            )
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return StudentContext(
            name=payload["name"],
            college_email=payload["college_email"],
            prn=payload["prn"],
            program=payload["program"],
            division=payload["division"],
            year=payload["year"],
            semester=payload["semester"],
            lab_batches=tuple(LabBatch(**item) for item in payload.get("lab_batches", [])),
        )
