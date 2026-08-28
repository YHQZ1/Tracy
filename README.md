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
tracy index
tracy ask "What assignments are due this week?"
tracy reminders
```

Run `tracy index` after syncing to extract and search downloaded course documents.

Tracy uses a local Ollama model for query planning and synthesized document answers. The planner translates natural language into a validated query plan; Tracy executes facts against the local snapshot. Install Ollama, run `ollama pull gemma3:4b`, and keep Ollama running. Configure `TRACY_OLLAMA_BASE_URL` and `TRACY_OLLAMA_MODEL` in `.env` if needed. If Ollama is unavailable, Tracy falls back to deterministic query heuristics and citation-rich retrieval results.
Document answers include the course, page or slide, snippet, and Moodle source URL.

On the first sync, Tracy opens a browser window. Sign in to Moodle there and
press Enter in the terminal. Tracy never asks for or stores your Moodle password.

## Architecture

See [`docs/architecture.md`](docs/architecture.md) and
[`docs/data-model.md`](docs/data-model.md).
