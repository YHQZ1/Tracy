"""Answer questions using structured Moodle data and indexed documents."""

from datetime import date
from pathlib import Path

from tracy.adapters.documents.index import JsonDocumentIndexStore
from tracy.application.query_plans import answer_from_query_plan, heuristic_query_plan
from tracy.config import get_settings
from tracy.domain.entities import DocumentChunk, SyncSnapshot
from tracy.domain.ports import AnswerComposer, QuestionPlanner
from tracy.persistence.json_store import JsonSnapshotStore


def _answer_from_snapshot(
    question: str, snapshot: SyncSnapshot, *, today: date | None = None
) -> str:
    answer = answer_from_query_plan(heuristic_query_plan(question), snapshot, today=today)
    return answer or (
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


def _default_planner() -> QuestionPlanner:
    settings = get_settings()
    from tracy.adapters.llm.planner import OllamaQuestionPlanner

    return OllamaQuestionPlanner(model=settings.ollama_model, base_url=settings.ollama_base_url)


async def answer_question(
    question: str,
    data_dir: Path,
    *,
    composer: AnswerComposer | None = None,
    planner: QuestionPlanner | None = None,
) -> str:
    """Answer a question using a query plan and local Moodle data."""

    snapshot = JsonSnapshotStore(data_dir).load()
    active_planner = (
        planner if planner is not None else _default_planner() if composer is None else None
    )
    plan = heuristic_query_plan(question)
    if active_planner is not None:
        try:
            plan = await active_planner.plan(
                question, tuple(course.name for course in snapshot.courses)
            )
        except RuntimeError:
            pass
    structured_answer = answer_from_query_plan(plan, snapshot)
    if structured_answer is not None:
        return structured_answer

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
