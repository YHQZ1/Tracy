# Tracy

Tracy is a local-first academic copilot for Moodle installations that were never
designed to feel coherent.

Moodle often contains the right information, but not in the right place. A
deadline may live inside an assignment page, instructions may be hidden inside a
PDF, the relevant activity may be locked to a lab batch, and attendance may be
displayed in a separate report. Tracy brings those pieces together while keeping
Moodle as the source of truth.

Tracy currently runs for one student on one local machine. It reads the Moodle
account you sign into, stores the resulting data locally, and answers questions
against that private snapshot.

## What Tracy can do today

Tracy supports four kinds of questions:

- Course questions: list enrolled courses and identify a course by name.
- Assignment questions: find assignments by course, due date, cutoff date, and
  submission status.
- Attendance questions: show course totals, individual history, absences,
  overall attendance, safe absence headroom, required future classes, and
  course-level skip suggestions.
- Document questions: search attached PDFs, PPTX files, DOCX files, and text
  files, then explain relevant material with course and page/slide sources.

Examples:

```
What assignments are due this week?
List my assignments for Compiler Construction Lab.
What is my attendance in DevOps Lab?
When was I absent?
What is my overall attendance?
How many classes can I miss to stay above 75%?
What classes can I skip and stay above 75%?
What is the syllabus of Compiler Construction?
What documents should I read for Unit 2?
```

The goal is not simply to make Moodle searchable. Tracy separates facts that
must be calculated exactly from documents that need interpretation:

```
Moodle
  ↓ authenticated browser session
Local snapshot
  ├── typed courses, assignments, and attendance
  └── downloaded document files
        ↓
  ├── deterministic structured queries
  └── document retrieval → local Ollama explanation
```

## Quick start

### Requirements

- macOS or another environment that can run Chromium and Python 3.12+
- uv
- A Moodle account with access to the courses you want to read
- Ollama for local question planning and document answers

Tracy does not require an OpenAI, Groq, or Gemini API key. Ollama runs the
model locally. The default model is gemma3:4b, but any compatible local model
can be configured.

### Install

```
uv sync --all-extras
uv run playwright install chromium
ollama pull gemma3:4b
```

Start Ollama, then configure the Moodle URL if it is not already in .env:

```
TRACY_MOODLE_BASE_URL=https://your-moodle.example.com uv run tracy sync
```

The first sync opens a dedicated browser window. Sign into Moodle there and
press Enter in the terminal after the authenticated page is open. Tracy never
asks for or stores your Moodle password.

### First sync and setup

After syncing, save the academic context Tracy needs to distinguish activities
belonging to you from activities belonging to another batch:

```
uv run tracy setup
```

The setup records:

- Name
- College email
- PRN
- Program
- Division
- Year
- Semester
- One lab batch for each detected lab course

This matters because Moodle commonly mixes several activity patterns. One course
may use BDA-1 and BDA-2, another may use L1 and L2, and another may use
division-based batches such as A1, B2, or C3.

When Tracy sees activities with the same name, it follows this rule:

1. Use the activity in the configured student batch when one exists.
2. Otherwise use the general activity.
3. Do not include another explicit batch as a fallback.

The context is local profile data, not conversational memory. It is stored in
data/student-context.json, which is ignored by Git.

## Everyday commands

```
# Refresh the local Moodle snapshot
uv run tracy sync

# Extract downloaded documents into the local search index
uv run tracy index

# Ask one question
uv run tracy ask "What assignments are due this week?"

# Inspect overdue and near-term actionable assignments
uv run tracy reminders

# Start the interactive shell
uv run tracy
```

Inside the interactive shell:

```
tracy> What is my overall attendance?
tracy> Which classes did I miss?
tracy> /sync
tracy> /index
tracy> /reminders
tracy> /help
tracy> /exit
```

The shell is intended to become Tracy's primary interface. Slash commands are
operational actions; ordinary text is treated as a question.

## How the AI is used

Tracy uses local Ollama in two narrow places:

1. Query planning. Ollama translates a natural-language question into a
   validated plan such as attendance + max_misses + 75% or assignments +
   next_7_days + course.
2. Document answering. Tracy retrieves matching document chunks and gives only
   those chunks to Ollama to explain.

Structured Moodle facts do not depend on an LLM to be correct. Dates, course
filters, attendance percentages, absence projections, and batch selection are
executed by Python against typed records. If Ollama is unavailable, Tracy falls
back to deterministic query heuristics and citation-rich retrieval output.

Tracy does not currently use autonomous agents, LangChain, or LangGraph. There is
no tool-calling loop making up actions. Application orchestration is ordinary
code so that a question about attendance cannot turn into an unreviewed write
to Moodle.

## Retrieval: what RAG means here

The current document pipeline is a small, local retrieval-augmented generation
system:

1. Sync downloads accessible Moodle documents.
2. tracy index extracts text and divides it into page/slide-aware chunks.
3. A deterministic lexical index ranks chunks using document, course, and text
   terms.
4. Ollama explains the selected chunks when a generated answer is useful.
5. Tracy appends document names, courses, pages/slides, and Moodle source URLs.

This is intentionally lexical RAG, not embedding-based vector RAG yet. The
repository is prepared for a stronger retrieval layer later, but the first
version favors inspectability and local operation over infrastructure.

## Attendance semantics

Tracy follows the institution's displayed overall attendance formula:

```
overall attendance = total attended sessions / total sessions × 100
```

Marked sessions are retained as Moodle metadata, but they are not used as the
overall denominator. A course with no sessions has an unavailable percentage
rather than a misleading zero.

Attendance projections are calculated locally. For a strict request such as
“stay above 80%”, Tracy finds the largest number of additional absences for
which:

```
attended sessions / (total sessions + additional absences) > 80%
```

Course-level skip suggestions are a separate view: they rank courses by their
individual buffer above the chosen threshold. They do not claim that skipping
one course changes the institution's overall attendance policy.

Individual history is collected only from attendance activities visible to the
signed-in student. Locked or faculty-only activities cannot be recovered by
Tracy, even if another batch's page appears in the course.

## Reminders

tracy reminders currently provides the first reminder slice from trusted Moodle
dates:

- Overdue assignments that still appear to require action
- Assignments due today through the next six days
- Due dates, cutoff dates, and submission statuses
- Course names and direct Moodle links
- A separate note for assignments without due dates

Assignments clearly marked as submitted, graded, returned, or completed are
excluded from actionable reminders. Reminder generation is deterministic and
does not ask the LLM to invent deadlines.

Scheduled sync can also deliver native macOS notifications. The scheduler enables
notifications automatically; each run sends one grouped alert for newly actionable
assignments and records sent reminder keys in data/notification-state.json so
repeated runs do not spam you. The regular reminder command still reads the latest
local snapshot; run tracy sync when Moodle data may have changed.

## Privacy and safety

Tracy is local-first by design:

- Moodle login happens manually in a dedicated Playwright browser profile.
- Passwords are never requested by Tracy and are not written to the repository.
- Moodle session data, downloaded files, snapshots, indexes, and student context
  remain under data/, which is ignored by Git.
- Tracy is read-only with respect to Moodle in the current version.
- Document text is treated as untrusted content. Instructions inside a PDF or
  presentation are context to explain, not commands for Tracy to execute.
- Source metadata is retained so answers can be checked against Moodle.

Before sharing a snapshot, browser profile, document index, or terminal output,
check it for personal information such as your name, PRN, email address, course
links, and session data.

## Configuration

Settings use the TRACY\_ environment prefix and can be placed in .env:

```
TRACY_MOODLE_BASE_URL=https://your-moodle.example.com
TRACY_DATA_DIR=data
TRACY_TIMEZONE=Asia/Kolkata
TRACY_NOTIFICATIONS_ENABLED=false
TRACY_OLLAMA_BASE_URL=http://localhost:11434
TRACY_OLLAMA_MODEL=gemma3:4b
```

Useful settings include:

- TRACY_MOODLE_BASE_URL — Moodle installation URL
- TRACY_DATA_DIR — local snapshot, browser profile, downloads, and index root
- TRACY_TIMEZONE — timezone used when displaying dates and reminders
- TRACY_NOTIFICATIONS_ENABLED — enable native macOS notifications after sync; scheduled sync sets this automatically
- TRACY_OLLAMA_BASE_URL — local Ollama endpoint
- TRACY_OLLAMA_MODEL — local model used by the planner and composer

## Development

Install all development and document/browser dependencies:

```
uv sync --all-extras
uv run playwright install chromium
```

Run the checks:

```
uv run pytest -q
uv run ruff check .
git diff --check
```

The tests exercise public behavior with local fixtures. To make the suite
independent of a running Ollama process, use an unreachable local endpoint when
needed:

```
TRACY_OLLAMA_BASE_URL=http://127.0.0.1:9 uv run pytest -q
```

## Project shape

```
src/tracy/
├── domain/          Moodle-independent entities and query contracts
├── application/     Sync, indexing, reminders, and question use cases
├── adapters/
│   ├── moodle/      Authenticated browser ingestion
│   ├── documents/   File extraction and lexical retrieval
│   └── llm/         Ollama planning and answer composition
├── persistence/     Local JSON snapshot and student-context stores
├── retrieval/       Boundary for future structured/semantic retrieval
└── interfaces/      Typer CLI and interactive shell
tests/               Behavior-focused fixtures for the public seams
docs/                Architecture and data-model notes
```

See docs/architecture.md and docs/data-model.md for lower-level design.

## Current boundaries and roadmap

Tracy is a working local prototype, not yet a hosted multi-user service. The
next product milestones are:

1. Finish CLI command ergonomics and add tracy doctor.
2. Move the local snapshot from JSON to SQLite with migrations and incremental
   updates.
3. Improve Moodle-version/plugin coverage and sync observability.
4. Add embedding retrieval and evaluation datasets when lexical retrieval stops
   being sufficient.
5. Consider a web interface and multi-user isolation only after the local flow
   is reliable.

The guiding rule is simple: use AI where language is messy, and use typed,
testable code where the answer is a date, a count, a percentage, or a personal
filter.
