import asyncio

import typer
from rich.console import Console

from tracy import __version__
from tracy.application.answer_question import answer_question
from tracy.application.create_reminders import create_reminders
from tracy.application.index_documents import index_documents
from tracy.application.sync_moodle import sync_moodle
from tracy.config import get_settings

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
        snapshot = asyncio.run(sync_moodle(get_settings()))
    except (NotImplementedError, RuntimeError, ValueError) as error:
        console.print(f"[yellow]{error}[/yellow]")
    else:
        console.print(
            f"Synced {len(snapshot.courses)} courses, {len(snapshot.assignments)} assignments, "
            f"and {len(snapshot.documents)} documents."
        )


@app.command()
def ask(question: str) -> None:
    """Ask a question about the authenticated student's Moodle data."""

    try:
        answer = asyncio.run(answer_question(question, get_settings().data_dir))
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        console.print(f"[yellow]{error}[/yellow]")
    else:
        console.print(answer)


@app.command(name="index")
def index() -> None:
    """Extract and index downloaded Moodle documents."""

    try:
        document_index = index_documents(get_settings().data_dir)
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        console.print(f"[yellow]{error}[/yellow]")
    else:
        console.print(f"Indexed {len(document_index.chunks)} document chunks.")


@app.command()
def reminders() -> None:
    """Create or inspect reminders."""

    try:
        asyncio.run(create_reminders())
    except NotImplementedError as error:
        console.print(f"[yellow]{error}[/yellow]")


def main() -> None:
    app()
