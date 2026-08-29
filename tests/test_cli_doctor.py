from typer.testing import CliRunner

from tracy.application.doctor import DoctorCheck, DoctorReport
from tracy.config import Settings
from tracy.interfaces import cli


def test_doctor_command_prints_report_and_returns_failure_for_blockers(monkeypatch) -> None:
    monkeypatch.setattr(cli, "get_settings", lambda: Settings(moodle_base_url="https://moodle.example"))
    monkeypatch.setattr(
        cli,
        "run_doctor",
        lambda settings: DoctorReport((DoctorCheck("Snapshot", "fail", "missing"),)),
    )

    result = CliRunner().invoke(cli.app, ["doctor"])

    assert result.exit_code == 1
    assert "FAIL Snapshot: missing" in result.stdout


def test_doctor_command_returns_success_when_no_blockers(monkeypatch) -> None:
    monkeypatch.setattr(cli, "get_settings", lambda: Settings(moodle_base_url="https://moodle.example"))
    monkeypatch.setattr(
        cli,
        "run_doctor",
        lambda settings: DoctorReport((DoctorCheck("Snapshot", "ok", "fresh"),)),
    )

    result = CliRunner().invoke(cli.app, ["doctor"])

    assert result.exit_code == 0
    assert "Doctor: no blocking problems found." in result.stdout
