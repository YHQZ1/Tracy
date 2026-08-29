"""Install and manage Tracy's macOS launchd sync job."""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

LAUNCH_AGENT_LABEL = "com.tracy.moodle-sync"
DEFAULT_INTERVAL_HOURS = 6
Launchctl = Callable[[list[str]], None]


def default_project_dir() -> Path:
    """Return the repository root containing the installed Tracy package."""

    return Path(__file__).resolve().parents[3]


def launch_agent_path(launch_agents_dir: Path | None = None) -> Path:
    directory = launch_agents_dir or Path.home() / "Library" / "LaunchAgents"
    return directory / f"{LAUNCH_AGENT_LABEL}.plist"


def render_launchd_plist(
    *,
    project_dir: Path,
    python_executable: str,
    data_dir: Path,
    interval_hours: int = DEFAULT_INTERVAL_HOURS,
) -> bytes:
    """Render a launchd user-agent plist for unattended headless sync."""

    if interval_hours <= 0:
        raise ValueError("Schedule interval must be greater than zero hours.")
    absolute_project_dir = project_dir.expanduser().resolve()
    absolute_data_dir = data_dir.expanduser().resolve()
    payload = {
        "Label": LAUNCH_AGENT_LABEL,
        "ProgramArguments": [python_executable, "-m", "tracy", "sync"],
        "WorkingDirectory": str(absolute_project_dir),
        "StartInterval": interval_hours * 60 * 60,
        "EnvironmentVariables": {
            "TRACY_DATA_DIR": str(absolute_data_dir),
            "TRACY_MOODLE_HEADLESS": "true",
        },
        "ProcessType": "Background",
        "StandardOutPath": str(absolute_data_dir / "scheduler.log"),
        "StandardErrorPath": str(absolute_data_dir / "scheduler-error.log"),
    }
    return plistlib.dumps(payload, fmt=plistlib.FMT_XML, sort_keys=False)


def _run_launchctl(arguments: list[str]) -> None:
    subprocess.run(["launchctl", *arguments], check=True)


def _bootout_existing(launchctl: Launchctl, user_domain: str) -> None:
    try:
        launchctl(["bootout", f"{user_domain}/{LAUNCH_AGENT_LABEL}"])
    except (OSError, subprocess.CalledProcessError):
        pass


def install_schedule(
    *,
    project_dir: Path,
    python_executable: str = sys.executable,
    data_dir: Path = Path("data"),
    interval_hours: int = DEFAULT_INTERVAL_HOURS,
    launch_agents_dir: Path | None = None,
    launchctl: Launchctl | None = None,
    user_domain: str | None = None,
) -> Path:
    """Install or replace Tracy's launchd user agent."""

    if sys.platform != "darwin":
        raise RuntimeError("Scheduled sync installation is currently supported on macOS only.")
    active_launchctl = launchctl or _run_launchctl
    domain = user_domain or f"gui/{os.getuid()}"
    plist_path = launch_agent_path(launch_agents_dir)
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    data_dir.expanduser().resolve().mkdir(parents=True, exist_ok=True)
    plist_path.write_bytes(
        render_launchd_plist(
            project_dir=project_dir,
            python_executable=python_executable,
            data_dir=data_dir,
            interval_hours=interval_hours,
        )
    )
    _bootout_existing(active_launchctl, domain)
    active_launchctl(["bootstrap", domain, str(plist_path)])
    return plist_path


def remove_schedule(
    *,
    launch_agents_dir: Path | None = None,
    launchctl: Launchctl | None = None,
    user_domain: str | None = None,
) -> Path:
    """Unload and remove Tracy's launchd user agent."""

    active_launchctl = launchctl or _run_launchctl
    domain = user_domain or f"gui/{os.getuid()}"
    plist_path = launch_agent_path(launch_agents_dir)
    _bootout_existing(active_launchctl, domain)
    plist_path.unlink(missing_ok=True)
    return plist_path


def schedule_is_installed(launch_agents_dir: Path | None = None) -> bool:
    return launch_agent_path(launch_agents_dir).exists()

