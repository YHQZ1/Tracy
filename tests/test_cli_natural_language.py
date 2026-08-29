from collections.abc import Iterator

import pytest

from tracy.interfaces import cli


@pytest.mark.parametrize(
    "command",
    ("reminders", "show reminders", "my reminders", "show my reminders"),
)
def test_interactive_shell_routes_natural_reminder_commands(
    monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    inputs: Iterator[str] = iter((command, "/exit"))
    reminder_calls: list[bool] = []
    question_calls: list[str] = []

    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    monkeypatch.setattr(cli, "reminders", lambda: reminder_calls.append(True))
    monkeypatch.setattr(cli, "ask", lambda question: question_calls.append(question))

    cli.interactive_shell()

    assert reminder_calls == [True]
    assert question_calls == []


def test_interactive_shell_handles_conversational_phrases_without_asking_moodle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs: Iterator[str] = iter(("hi", "thanks", "okay", "bye"))
    question_calls: list[str] = []
    messages: list[str] = []

    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    monkeypatch.setattr(cli, "ask", lambda question: question_calls.append(question))
    monkeypatch.setattr(cli.console, "print", lambda message="": messages.append(str(message)))

    cli.interactive_shell()

    assert question_calls == []
    assert any("How can I help" in message for message in messages)
    assert any("welcome" in message for message in messages)
    assert any("Goodbye" in message for message in messages)
