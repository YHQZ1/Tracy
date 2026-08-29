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
    no_args_is_help=False,
)
console = Console()

_NATURAL_REMINDER_COMMANDS = {
    "reminders",
    "show reminders",
    "my reminders",
    "show my reminders",
}
_CONVERSATIONAL_RESPONSES = {
    "hi": "Hi! How can I help?",
    "hello": "Hi! How can I help?",
    "hey": "Hi! How can I help?",
    "hi tracy": "Hi! How can I help?",
    "hello tracy": "Hi! How can I help?",
    "hey tracy": "Hi! How can I help?",
    "thanks": "You're welcome!",
    "thank you": "You're welcome!",
    "thanks tracy": "You're welcome!",
    "thank you tracy": "You're welcome!",
    "okay": "Got it.",
    "ok": "Got it.",
    "cool": "Got it.",
    "alright": "Got it.",
    "all right": "Got it.",
    "got it": "Got it.",
}
_GOODBYE_PHRASES = {"bye", "goodbye", "see you", "good night"}


def _print_shell_help() -> None:
    console.print("Tracy commands:")
    console.print("  /sync       Synchronize data from Moodle")
    console.print("  /index      Rebuild the document index")
    console.print("  /setup      Update your local student context")
    console.print("  /reminders  Show overdue and near-term assignment reminders")
    console.print("  /help       Show this help")
    console.print("  /exit       Leave the Tracy shell")


def interactive_shell() -> None:
    """Run an interactive loop over Tracy's existing CLI operations."""

    console.print("Tracy interactive shell. Type /help for commands or /exit to quit.")
    while True:
        try:
            question = input("tracy> ").strip()
            normalized_question = " ".join(question.casefold().split())
        except (EOFError, KeyboardInterrupt):
            console.print()
            return
        if not question:
            continue
        if (
            normalized_question in {"/exit", "/quit", "exit", "quit"}
            or normalized_question in _GOODBYE_PHRASES
        ):
            if normalized_question in _GOODBYE_PHRASES:
                console.print("Goodbye!")
            return
        if normalized_question in {"/help", "help"}:
            _print_shell_help()
        elif normalized_question == "/sync":
            sync()
        elif normalized_question == "/index":
            index()
        elif normalized_question == "/setup":
            setup()
        elif (
            normalized_question == "/reminders"
            or normalized_question in _NATURAL_REMINDER_COMMANDS
        ):
            reminders()
        elif normalized_question in _CONVERSATIONAL_RESPONSES:
            console.print(_CONVERSATIONAL_RESPONSES[normalized_question])
        elif normalized_question.startswith("/"):
            console.print(f"[yellow]Unknown command: {question}[/yellow]")
        else:
            ask(question)


@app.callback(invoke_without_command=True)
def _run_shell_when_no_command(ctx: typer.Context) -> None:
    """Open the interactive shell when Tracy is invoked without a subcommand."""

    if ctx.invoked_subcommand is None:
        interactive_shell()


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
            f"{len(snapshot.documents)} documents, and "
            f"{len(snapshot.attendance)} attendance summaries, and "
            f"{len(snapshot.attendance_records)} attendance records."
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


@app.command()
def shell() -> None:
    """Open the interactive Tracy shell."""

    interactive_shell()


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
    """Show overdue and near-term assignment reminders."""

    settings = get_settings()
    try:
        report = asyncio.run(
            create_reminders(settings.data_dir, timezone=settings.timezone)
        )
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        console.print(f"[yellow]{error}[/yellow]")
    else:
        console.print(report)


def main() -> None:
    app()
