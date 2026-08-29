from datetime import UTC, datetime
from pathlib import Path
from plistlib import dumps
from types import SimpleNamespace

import httpx

from tracy.adapters.documents.index import DocumentIndex, JsonDocumentIndexStore
from tracy.application import doctor as doctor_module
from tracy.config import Settings
from tracy.domain.entities import Course, DocumentChunk, SyncSnapshot
from tracy.domain.student import LabBatch, StudentContext
from tracy.persistence.json_store import JsonSnapshotStore
from tracy.persistence.student_context_store import JsonStudentContextStore


class HealthyOllamaResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, list[dict[str, str]]]:
        return {"models": [{"name": "gemma3:4b"}]}


def _healthy_settings(tmp_path: Path) -> Settings:
    return Settings(
        moodle_base_url="https://moodle.example",
        data_dir=tmp_path / "data",
        moodle_profile_dir=tmp_path / "profile",
        ollama_base_url="http://ollama.example",
        ollama_model="gemma3:4b",
        timezone="UTC",
    )


def _write_healthy_state(settings: Settings, scheduler_path: Path) -> None:
    settings.data_dir.mkdir(parents=True)
    settings.moodle_profile_dir.mkdir(parents=True)
    (settings.moodle_profile_dir / "Default").mkdir()
    (settings.moodle_profile_dir / "Default" / "Preferences").write_text("{}")
    JsonSnapshotStore(settings.data_dir).save(
        SyncSnapshot(
            synced_at=datetime(2026, 8, 29, 9, tzinfo=UTC),
            courses=(Course(id="db", name="Databases"),),
        )
    )
    JsonDocumentIndexStore(settings.data_dir).save(
        DocumentIndex(
            (
                DocumentChunk(
                    id="chunk",
                    document_id="doc",
                    course_id="db",
                    course_name="Databases",
                    document_name="Syllabus.pdf",
                    source_url="https://moodle.example/doc",
                    text="Course syllabus",
                    page=1,
                ),
            )
        )
    )
    JsonStudentContextStore(settings.data_dir).save(
        StudentContext(
            name="Test Student",
            college_email="student@example.edu",
            prn="TEST123",
            program="Computer Science",
            division="B",
            year=4,
            semester=7,
            lab_batches=(
                LabBatch(course_id="db", course_name="Databases", batch="L1"),
            ),
        )
    )
    scheduler_path.write_bytes(
        dumps(
            {
                "Label": "com.tracy.moodle-sync",
                "EnvironmentVariables": {
                    "TRACY_NOTIFICATIONS_ENABLED": "true",
                },
            }
        )
    )


def test_doctor_reports_a_healthy_setup(tmp_path, monkeypatch) -> None:
    settings = _healthy_settings(tmp_path)
    scheduler_path = tmp_path / "com.tracy.moodle-sync.plist"
    _write_healthy_state(settings, scheduler_path)

    monkeypatch.setattr(doctor_module.sys, "platform", "darwin")
    monkeypatch.setattr(doctor_module, "_playwright_available", lambda: True)
    monkeypatch.setattr(doctor_module.shutil, "which", lambda name: "/usr/bin/osascript")
    monkeypatch.setattr(doctor_module, "launch_agent_path", lambda: scheduler_path)
    monkeypatch.setattr(doctor_module, "schedule_is_installed", lambda: True)
    monkeypatch.setattr(doctor_module.httpx, "get", lambda *args, **kwargs: HealthyOllamaResponse())
    monkeypatch.setattr(
        doctor_module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="state = running"),
    )

    report = doctor_module.run_doctor(settings, now=datetime(2026, 8, 29, 10, tzinfo=UTC))

    assert report.ok
    assert all(check.status == "ok" for check in report.checks)
    assert "OK Configuration" in report.render()
    assert "OK Scheduled sync" in report.render()


def _offline_ollama(*args, **kwargs):
    raise httpx.ConnectError("offline")


def test_doctor_reports_missing_setup_with_actionable_fixes(tmp_path, monkeypatch) -> None:
    settings = Settings(
        moodle_base_url="",
        data_dir=tmp_path / "data",
        moodle_profile_dir=tmp_path / "profile",
        ollama_base_url="http://ollama.example",
        timezone="UTC",
    )

    monkeypatch.setattr(doctor_module.sys, "platform", "darwin")
    monkeypatch.setattr(doctor_module, "_playwright_available", lambda: False)
    monkeypatch.setattr(doctor_module.shutil, "which", lambda name: None)
    monkeypatch.setattr(doctor_module.httpx, "get", _offline_ollama)
    monkeypatch.setattr(doctor_module, "schedule_is_installed", lambda: False)

    report = doctor_module.run_doctor(settings, now=datetime(2026, 8, 29, 10, tzinfo=UTC))

    assert not report.ok
    rendered = report.render()
    assert "FAIL Configuration" in rendered
    assert "Run `uv run tracy sync`" in rendered
    assert "WARN Ollama" in rendered
    assert "Run `tracy setup`" in rendered
