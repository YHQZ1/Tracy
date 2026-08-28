# Tracy

Tracy is a headless AI companion for Moodle course data, documents, and reminders.

It is designed to help students find reliable answers across courses, assignments,
announcements, grades, attendance, and attached documents without replacing Moodle
as the source of truth.

## Current status

The repository contains the initial Python package and architecture scaffold. Moodle
integration, persistence, document indexing, AI workflows, and reminders are not
implemented yet.

## Development

```bash
uv sync --all-extras
uv run tracy --help
uv run pytest
uv run ruff check .
```

The first interface is intentionally a CLI:

```bash
tracy sync
tracy ask "What assignments are due this week?"
tracy reminders
```

## Architecture

See [`docs/architecture.md`](docs/architecture.md) and
[`docs/data-model.md`](docs/data-model.md).
