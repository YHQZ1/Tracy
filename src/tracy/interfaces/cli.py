import asyncio
from datetime import UTC, datetime

import typer
from rich.console import Console

from tracy import __version__
from tracy.application.answer_question import answer_question
from tracy.application.create_reminders import create_reminders
from tracy.application.index_documents import index_documents
from tracy.application.setup_student_context import collect_student_context
from tracy.application.sync_moodle import sync_moodle
from tracy.config import get_settings
from tracy.domain.entities import SyncSnapshot
from tracy.persistence.json_store import JsonSnapshotStore
from tracy.persistence.student_context_store import JsonStudentContextStore

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
def setup() -> None:
    """Set up the local student identity and academic context."""

    settings = get_settings()
    try:
        snapshot = JsonSnapshotStore(settings.data_dir).load()
    except FileNotFoundError:
        snapshot = SyncSnapshot(synced_at=datetime.now(UTC))
        console.print(
            "[yellow]No Moodle snapshot found. Run `tracy sync` first to configure "
            "lab batches.[/yellow]"
        )

    def ask(message: str, default: str | None = None) -> str:
        if default is None:
            return typer.prompt(message)
        return typer.prompt(message, default=default, show_default=False)

    try:
        context = collect_student_context(tuple(snapshot.courses), ask)
        JsonStudentContextStore(settings.data_dir).save(context)
    except (ValueError, typer.Abort) as error:
        console.print(f"[yellow]{error}[/yellow]")
    else:
        console.print(
            f"Saved student context for {context.name} with {len(context.lab_batches)} lab batches."
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
