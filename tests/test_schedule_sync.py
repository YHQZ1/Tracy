from pathlib import Path
from plistlib import loads

from tracy.application.schedule_sync import (
    LAUNCH_AGENT_LABEL,
    install_schedule,
    render_launchd_plist,
)


def test_render_launchd_plist_runs_headless_sync_on_an_interval(tmp_path: Path) -> None:
    plist = loads(
        render_launchd_plist(
            project_dir=tmp_path / "Tracy",
            python_executable="/venv/bin/python",
            data_dir=tmp_path / "data",
            interval_hours=6,
        )
    )

    assert plist["Label"] == LAUNCH_AGENT_LABEL
    assert plist["ProgramArguments"] == [
        "/venv/bin/python",
        "-m",
        "tracy",
        "sync",
    ]
    assert plist["WorkingDirectory"] == str(tmp_path / "Tracy")
    assert plist["StartInterval"] == 21_600
    assert plist["EnvironmentVariables"]["TRACY_MOODLE_HEADLESS"] == "true"
    assert plist["EnvironmentVariables"]["TRACY_NOTIFICATIONS_ENABLED"] == "true"
    assert plist["StandardOutPath"] == str(tmp_path / "data" / "scheduler.log")
    assert plist["StandardErrorPath"] == str(tmp_path / "data" / "scheduler-error.log")


def test_install_schedule_writes_job_and_bootstraps_launchd(tmp_path: Path) -> None:
    launchctl_calls: list[list[str]] = []

    def launchctl(arguments: list[str]) -> None:
        launchctl_calls.append(arguments)

    plist_path = install_schedule(
        project_dir=tmp_path / "Tracy",
        python_executable="/venv/bin/python",
        data_dir=tmp_path / "data",
        interval_hours=2,
        launch_agents_dir=tmp_path / "LaunchAgents",
        launchctl=launchctl,
        user_domain="gui/501",
    )

    assert plist_path.exists()
    assert loads(plist_path.read_bytes())["StartInterval"] == 7_200
    assert launchctl_calls == [
        ["bootout", "gui/501/com.tracy.moodle-sync"],
        ["bootstrap", "gui/501", str(plist_path)],
    ]
