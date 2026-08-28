from collections.abc import Iterator

import pytest

from tracy.interfaces import cli


def test_interactive_shell_routes_questions_and_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    inputs: Iterator[str] = iter(("What is my attendance?", "/exit"))
    answers: list[str] = []

    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    monkeypatch.setattr(cli, "ask", lambda question: answers.append(question))

    cli.interactive_shell()

    assert answers == ["What is my attendance?"]


def test_interactive_shell_handles_help_and_eof(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    inputs: Iterator[str] = iter(("/help",))

    def input_then_eof(_: str) -> str:
        try:
            return next(inputs)
        except StopIteration as error:
            raise EOFError from error

    monkeypatch.setattr("builtins.input", input_then_eof)

    cli.interactive_shell()

    output = capsys.readouterr().out
    assert "/sync" in output
    assert "/exit" in output
