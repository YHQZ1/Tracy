import asyncio

import typer
from rich.console import Console

from tracy import __version__
from tracy.application.answer_question import answer_question
from tracy.application.create_reminders import create_reminders
from tracy.application.sync_moodle import sync_moodle

app = typer.Typer(
    name="tracy",
    help="A headless AI companion for Moodle course data, documents, and reminders.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def version() -> None:
    """Print the Tracy version."""

    console.print(__version__)


@app.command()
def sync() -> None:
    """Synchronize data from Moodle."""

    try:
        asyncio.run(sync_moodle())
    except NotImplementedError as error:
        console.print(f"[yellow]{error}[/yellow]")


@app.command()
def ask(question: str) -> None:
    """Ask a question about the authenticated student's Moodle data."""

    try:
        answer = asyncio.run(answer_question(question))
    except NotImplementedError as error:
        console.print(f"[yellow]{error}[/yellow]")
    else:
        console.print(answer)


@app.command()
def reminders() -> None:
    """Create or inspect reminders."""

    try:
        asyncio.run(create_reminders())
    except NotImplementedError as error:
        console.print(f"[yellow]{error}[/yellow]")


def main() -> None:
    app()
