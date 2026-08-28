"""Answer questions using structured Moodle data and indexed documents."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from tracy.adapters.documents.index import JsonDocumentIndexStore
from tracy.config import get_settings
from tracy.domain.entities import Assignment, DocumentChunk, SyncSnapshot
from tracy.domain.ports import AnswerComposer
from tracy.persistence.json_store import JsonSnapshotStore


def _format_assignment(assignment: Assignment, course_name: str | None = None) -> str:
    due = (
        assignment.due_at.strftime("%a, %d %b %Y at %I:%M %p")
        if assignment.due_at
        else "no due date"
    )
    course = f" — {course_name}" if course_name else ""
    source = f" — source: {assignment.source_url}" if assignment.source_url else ""
    return f"- {assignment.name}{course} — {due}{source}"


def _calendar_week_bounds(today: date) -> tuple[date, date]:
    start = today - timedelta(days=today.weekday())
    return start, start + timedelta(days=7)


def _upcoming_this_week_bounds(today: date) -> tuple[date, date]:
    start, end = _calendar_week_bounds(today)
    return max(today, start), end


def _answer_from_snapshot(
    question: str, snapshot: SyncSnapshot, *, today: date | None = None
) -> str:
    normalized = question.casefold()
    if "course" in normalized or "enrolled" in normalized:
        if not snapshot.courses:
            return "I could not find any courses in the latest Moodle snapshot."
        lines = [f"You are enrolled in {len(snapshot.courses)} courses:"]
        lines.extend(f"- {course.name}" for course in snapshot.courses)
        return "\n".join(lines)

    if "assignment" in normalized or "deadline" in normalized or "due" in normalized:
        assignments = list(snapshot.assignments)
        if "this week" in normalized:
            current_date = today or datetime.now().date()
            if "were due" in normalized or "was due" in normalized:
                start, end = _calendar_week_bounds(current_date)
            else:
                start, end = _upcoming_this_week_bounds(current_date)
            assignments = [
                item for item in assignments if item.due_at and start <= item.due_at.date() < end
            ]
        assignments.sort(key=lambda item: item.due_at or datetime.max.replace(tzinfo=UTC))
        if not assignments:
            return "I found no matching assignments in the latest Moodle snapshot."
        course_names = {course.id: course.name for course in snapshot.courses}
        return "Assignments:\n" + "\n".join(
            _format_assignment(item, course_names.get(item.course_id)) for item in assignments
        )

    return (
        "The current Tracy slice can answer course-list and assignment-deadline questions. "
        "Run `tracy sync` first if the snapshot is out of date."
    )


def _document_context(results: list[DocumentChunk]) -> str:
    context: list[str] = []
    for index, chunk in enumerate(results, 1):
        location = f", page/slide {chunk.page}" if chunk.page else ""
        context.append(
            f"[{index}] {chunk.document_name} — {chunk.course_name}{location}\n"
            f"Source URL: {chunk.source_url}\n"
            f"Excerpt:\n{chunk.text}"
        )
    return "\n\n".join(context)


def _source_appendix(results: list[DocumentChunk]) -> str:
    grouped: dict[tuple[str, str, str], list[tuple[int, int | None]]] = {}
    for index, chunk in enumerate(results, 1):
        key = (chunk.source_url, chunk.document_name, chunk.course_name)
        grouped.setdefault(key, []).append((index, chunk.page))

    lines = ["Sources:"]
    for (source_url, document_name, course_name), references in grouped.items():
        citation_numbers = ", ".join(f"[{index}]" for index, _ in references)
        pages = sorted({page for _, page in references if page is not None})
        location = f" (pages/slides {', '.join(map(str, pages))})" if pages else ""
        label = f"{document_name} — {course_name}{location}"
        source = f"[link={source_url}]{label}[/link]" if source_url else label
        lines.append(f"- {citation_numbers} {source}")
    return "\n".join(lines)


def _with_sources(answer: str, results: list[DocumentChunk]) -> str:
    return f"{answer.rstrip()}\n\n{_source_appendix(results)}"


def _retrieval_answer(results: list[DocumentChunk]) -> str:
    lines = ["Relevant documents:"]
    for chunk in results:
        location = f", page/slide {chunk.page}" if chunk.page else ""
        lines.append(f"- {chunk.document_name} — {chunk.course_name}{location}")
        lines.append(f"  {chunk.text[:320]}")
    return _with_sources("\n".join(lines), results)


def _default_composer() -> AnswerComposer:
    settings = get_settings()
    from tracy.adapters.llm.ollama import OllamaAnswerComposer

    return OllamaAnswerComposer(model=settings.ollama_model, base_url=settings.ollama_base_url)


async def answer_question(
    question: str, data_dir: Path, *, composer: AnswerComposer | None = None
) -> str:
    """Answer supported structured questions from the local snapshot."""

    snapshot = JsonSnapshotStore(data_dir).load()
    answer = _answer_from_snapshot(question, snapshot)
    if not answer.startswith("The current Tracy slice"):
        return answer

    try:
        results = JsonDocumentIndexStore(data_dir).load().search(question)
    except FileNotFoundError as error:
        return str(error)
    if not results:
        return "I could not find relevant documents in the latest document index."

    if composer is None:
        try:
            answer = await _default_composer().compose(question, _document_context(results))
        except RuntimeError:
            return _retrieval_answer(results)
    else:
        answer = await composer.compose(question, _document_context(results))
    return _with_sources(answer, results)
