"""Read-only diagnostics for Tracy's local runtime."""

from __future__ import annotations

import importlib.util
import json
import os
import plistlib
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import httpx

from tracy.adapters.documents.index import JsonDocumentIndexStore
from tracy.application.schedule_sync import (
    LAUNCH_AGENT_LABEL,
    launch_agent_path,
    schedule_is_installed,
)
from tracy.config import Settings
from tracy.persistence.json_store import JsonSnapshotStore
from tracy.persistence.student_context_store import JsonStudentContextStore

CheckStatus = Literal["ok", "warn", "fail"]


@dataclass(frozen=True, slots=True)
class DoctorCheck:
    """One user-facing health check result."""

    name: str
    status: CheckStatus
    detail: str
    hint: str | None = None

    def render(self) -> str:
        line = f"{self.status.upper()} {self.name}: {self.detail}"
        if self.hint:
            line += f" — {self.hint}"
        return line


@dataclass(frozen=True, slots=True)
class DoctorReport:
    """The complete result of a Tracy health check."""

    checks: tuple[DoctorCheck, ...]

    @property
    def ok(self) -> bool:
        return not any(check.status == "fail" for check in self.checks)

    def render(self) -> str:
        lines = [check.render() for check in self.checks]
        if self.ok:
            lines.append("Doctor: no blocking problems found.")
        else:
            lines.append("Doctor: blocking problems found.")
        return "\n".join(lines)


def _configuration_check(settings: Settings) -> DoctorCheck:
    if not settings.moodle_base_url:
        return DoctorCheck(
            "Configuration",
            "fail",
            "Moodle URL is not configured.",
            "Set TRACY_MOODLE_BASE_URL in .env.",
        )
    if not settings.moodle_base_url.startswith(("http://", "https://")):
        return DoctorCheck(
            "Configuration",
            "fail",
            "Moodle URL must start with http:// or https://.",
            "Fix TRACY_MOODLE_BASE_URL in .env.",
        )
    return DoctorCheck("Configuration", "ok", "Moodle URL and local paths are configured.")


def _playwright_available() -> bool:
    return importlib.util.find_spec("playwright") is not None


def _browser_support_check() -> DoctorCheck:
    if _playwright_available():
        return DoctorCheck("Browser support", "ok", "Playwright is installed.")
    return DoctorCheck(
        "Browser support",
        "fail",
        "Playwright is not installed.",
        "Run `uv sync --extra browser` and `uv run playwright install chromium`.",
    )


def _profile_check(settings: Settings) -> DoctorCheck:
    profile_dir = settings.moodle_profile_dir.expanduser().resolve()
    if not profile_dir.exists():
        return DoctorCheck(
            "Moodle browser profile",
            "warn",
            f"Profile does not exist yet: {profile_dir}.",
            "Run `TRACY_MOODLE_HEADLESS=false uv run tracy sync` and sign in.",
        )
    if not any(profile_dir.iterdir()):
        return DoctorCheck(
            "Moodle browser profile",
            "warn",
            f"Profile is empty: {profile_dir}.",
            "Run a visible sync and sign in through Tracy's browser.",
        )
    return DoctorCheck("Moodle browser profile", "ok", f"Profile exists: {profile_dir}.")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _snapshot_check(settings: Settings, now: datetime) -> DoctorCheck:
    try:
        snapshot = JsonSnapshotStore(settings.data_dir).load()
    except FileNotFoundError:
        return DoctorCheck(
            "Moodle snapshot",
            "fail",
            "No local snapshot found.",
            "Run `uv run tracy sync`.",
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return DoctorCheck(
            "Moodle snapshot",
            "fail",
            "The local snapshot could not be read.",
            "Run `uv run tracy sync` to rebuild it.",
        )
    age_hours = max(0, (_as_utc(now) - _as_utc(snapshot.synced_at)).total_seconds() / 3600)
    detail = (
        f"{len(snapshot.courses)} courses, {len(snapshot.assignments)} assignments; "
        f"last synced {age_hours:.1f} hours ago."
    )
    if age_hours > 24:
        return DoctorCheck(
            "Moodle snapshot",
            "warn",
            detail,
            "Run `uv run tracy sync` to refresh Moodle data.",
        )
    return DoctorCheck("Moodle snapshot", "ok", detail)


def _index_check(settings: Settings) -> DoctorCheck:
    try:
        index = JsonDocumentIndexStore(settings.data_dir).load()
    except FileNotFoundError:
        return DoctorCheck(
            "Document index",
            "warn",
            "No document index found.",
            "Run `uv run tracy index` after syncing Moodle.",
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return DoctorCheck(
            "Document index",
            "warn",
            "The document index could not be read.",
            "Run `uv run tracy index` to rebuild it.",
        )
    if not index.chunks:
        return DoctorCheck(
            "Document index",
            "warn",
            "The document index contains no searchable chunks.",
            "Run `uv run tracy index` after syncing Moodle documents.",
        )
    snapshot_path = settings.data_dir / "snapshot.json"
    index_path = settings.data_dir / "document-index.json"
    if snapshot_path.exists() and index_path.stat().st_mtime < snapshot_path.stat().st_mtime:
        return DoctorCheck(
            "Document index",
            "warn",
            f"{len(index.chunks)} chunks are older than the latest snapshot.",
            "Run `uv run tracy index` to refresh document search.",
        )
    return DoctorCheck("Document index", "ok", f"{len(index.chunks)} searchable chunks.")


def _student_context_check(settings: Settings) -> DoctorCheck:
    try:
        context = JsonStudentContextStore(settings.data_dir).load()
    except FileNotFoundError:
        return DoctorCheck(
            "Student context",
            "warn",
            "Student identity and lab-batch context are not configured.",
            "Run `tracy setup` to scope assignments and attendance.",
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return DoctorCheck(
            "Student context",
            "fail",
            "Student context could not be read.",
            "Run `tracy setup` again.",
        )
    return DoctorCheck(
        "Student context",
        "ok",
        f"Configured with {len(context.lab_batches)} lab-batch mapping(s).",
    )


def _ollama_check(settings: Settings) -> DoctorCheck:
    base_url = settings.ollama_base_url.rstrip("/")
    try:
        response = httpx.get(f"{base_url}/api/tags", timeout=3.0)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return DoctorCheck(
            "Ollama",
            "warn",
            f"Ollama is not reachable at {base_url}.",
            "Start Ollama; Tracy can still answer deterministic queries without it.",
        )
    model_names = {item.get("name") for item in payload.get("models", [])}
    if settings.ollama_model not in model_names:
        return DoctorCheck(
            "Ollama",
            "warn",
            f"Ollama is reachable, but {settings.ollama_model} is not installed.",
            f"Run `ollama pull {settings.ollama_model}` or change TRACY_OLLAMA_MODEL.",
        )
    return DoctorCheck("Ollama", "ok", f"Reachable with model {settings.ollama_model}.")


def _load_scheduler_payload(path: Path) -> dict[str, object] | None:
    try:
        return plistlib.loads(path.read_bytes())
    except (OSError, plistlib.InvalidFileException):
        return None


def _scheduler_check() -> DoctorCheck:
    if sys.platform != "darwin":
        return DoctorCheck("Scheduled sync", "warn", "launchd is only available on macOS.")
    path = launch_agent_path()
    if not schedule_is_installed():
        return DoctorCheck(
            "Scheduled sync",
            "warn",
            "No Tracy launchd job is installed.",
            "Run `uv run tracy schedule install`.",
        )
    payload = _load_scheduler_payload(path)
    if payload is None:
        return DoctorCheck(
            "Scheduled sync",
            "fail",
            f"The launchd plist is unreadable: {path}.",
            "Run `uv run tracy schedule install`.",
        )
    try:
        result = subprocess.run(
            ["launchctl", "print", f"gui/{os.getuid()}/{LAUNCH_AGENT_LABEL}"],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        result = None
    if result is None or result.returncode != 0:
        return DoctorCheck(
            "Scheduled sync",
            "warn",
            "The plist exists but launchd is not reporting it as loaded.",
            "Run `uv run tracy schedule install`.",
        )
    environment = payload.get("EnvironmentVariables", {})
    if not isinstance(environment, dict):
        environment = {}
    if environment.get("TRACY_NOTIFICATIONS_ENABLED") != "true":
        return DoctorCheck(
            "Scheduled sync",
            "warn",
            "The loaded job is using an older configuration.",
            "Run `uv run tracy schedule install` to enable notifications.",
        )
    return DoctorCheck("Scheduled sync", "ok", "Installed and loaded by launchd.")


def _notifications_check(settings: Settings) -> DoctorCheck:
    if sys.platform != "darwin":
        return DoctorCheck("macOS notifications", "warn", "Native notifications require macOS.")
    if shutil.which("osascript") is None:
        return DoctorCheck(
            "macOS notifications",
            "warn",
            "The osascript command is unavailable.",
            "Use a macOS installation with Notification Center support.",
        )
    if settings.notifications_enabled:
        return DoctorCheck("macOS notifications", "ok", "Enabled for this Tracy process.")
    path = launch_agent_path()
    payload = _load_scheduler_payload(path) if path.exists() else None
    environment = payload.get("EnvironmentVariables", {}) if payload else {}
    if isinstance(environment, dict) and environment.get("TRACY_NOTIFICATIONS_ENABLED") == "true":
        return DoctorCheck("macOS notifications", "ok", "Available; scheduled sync enables them.")
    return DoctorCheck(
        "macOS notifications",
        "warn",
        "Available but disabled for manual syncs.",
        "The scheduled job enables notifications automatically.",
    )


def run_doctor(settings: Settings, *, now: datetime | None = None) -> DoctorReport:
    """Run non-mutating checks against Tracy's local configuration and state."""

    current = now or datetime.now(UTC)
    checks = (
        _configuration_check(settings),
        _browser_support_check(),
        _profile_check(settings),
        _snapshot_check(settings, current),
        _index_check(settings),
        _student_context_check(settings),
        _ollama_check(settings),
        _scheduler_check(),
        _notifications_check(settings),
    )
    return DoctorReport(checks)
