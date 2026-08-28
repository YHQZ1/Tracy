# Tracy architecture

Tracy is a headless, modular application for turning one student's Moodle data
into reliable answers and reminders.

## Runtime shape

The first deployment has a CLI entry point and a local browser session that share
the same package:

```text
tracy CLI       → manual sync, questions, and reminder inspection
browser profile → manual Moodle login, then authenticated reads
```

There is no frontend in the first version. An HTTP interface can be added later
without moving the domain or application logic.

## Module responsibilities

- `domain/` contains Moodle-independent entities and interfaces.
- `application/` owns use cases such as synchronization and question answering.
- `adapters/` contains concrete integrations with Moodle, LLMs, documents, and notifications.
- `persistence/` owns PostgreSQL, migrations, and repositories.
- `retrieval/` separates structured queries from semantic document search.
- `workflows/` owns stateful orchestration and retryable multi-step execution.
- `interfaces/` contains the CLI and future transport adapters.

## Data flow

```text
Moodle AJAX Web Services through a dedicated browser session
        ↓
Course and activity discovery
        ↓
Authenticated HTML activity pages and plugin files
        ↓
Sync and normalization
        ↓
Local JSON snapshot + document files (first slice)
        ↓
One-time local student context setup
        ↓
PostgreSQL + pgvector + object storage (later)
        ↓
Local Ollama query planning → validated structured query execution
        ↓
Structured or document retrieval
        ↓
LLM answer composition with citations
        ↓
Confirmed reminder creation
```

Structured facts such as courses, credits, attendance, grades, and assignment
dates must come from typed records. Semantic retrieval is for announcements,
instructions, and attached documents.

Student context such as PRN, program, division, year, semester, and per-lab
batch is collected once through `tracy setup` and stored locally. It is not
conversation memory. Future synchronization will attach Moodle group or batch
metadata to activities and attendance records, then apply this context through
deterministic filters before an LLM sees any answer data. The current sync
already maps assignment modules to Moodle section titles, so labels such as
`Batch L1`, `Batch L2`, and `A2` can scope assignment answers. A matching
batch-specific activity wins over a general activity with the same name.

## Initial constraints

- One Moodle installation.
- Student read-only access.
- Manual sign-in in a dedicated local browser profile.
- Student identity and academic context remain local to the user.
- No stored Moodle passwords, cookies, or session keys in the repository.
- No autonomous writes to Moodle.
- Every answer should retain source metadata.
- Dates inferred from documents require confirmation before reminders are created.
