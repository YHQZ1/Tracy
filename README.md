# Tracy

Tracy is a headless AI companion for Moodle course data, documents, and reminders.

It is designed to help students find reliable answers across courses, assignments,
announcements, grades, attendance, and attached documents without replacing Moodle
as the source of truth.

## Current status

The repository contains the first working Moodle ingestion slice. Tracy uses a
dedicated local Playwright profile: you sign in manually in the opened browser,
then Tracy reads accessible courses, activities, assignment pages, and files.
The profile and downloaded data stay under `data/` and are ignored by Git.

## Development

```bash
uv sync --all-extras
uv run playwright install chromium
uv run tracy --help
uv run pytest
uv run ruff check .
```

The first interface is intentionally a CLI:

```bash
TRACY_MOODLE_BASE_URL=https://your-moodle.example.com tracy sync
tracy ask "What assignments are due this week?"
tracy reminders
```

On the first sync, Tracy opens a browser window. Sign in to Moodle there and
press Enter in the terminal. Tracy never asks for or stores your Moodle password.

## Architecture

See [`docs/architecture.md`](docs/architecture.md) and
[`docs/data-model.md`](docs/data-model.md).
