import pytest

from tracy.adapters.llm.planner import OllamaQuestionPlanner
from tracy.application.query_plans import heuristic_query_plan


class FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return {"message": {"content": self.content}}


class FakeClient:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.request: tuple[str, dict] | None = None

    async def post(self, path: str, *, json: dict) -> FakeResponse:
        self.request = (path, json)
        return self.response


@pytest.mark.asyncio
async def test_ollama_planner_returns_validated_query_plan() -> None:
    client = FakeClient(
        FakeResponse(
            '{"intent":"assignments","time_range":"next_7_days",'
            '"direction":"upcoming","fields":["due_date","cutoff_date",'
            '"submission_status"],"group_by":"course","course_query":null}'
        )
    )

    plan = await OllamaQuestionPlanner(model="test-model", client=client).plan(
        "What assignments are due next week?", ("Databases",)
    )

    assert plan.intent == "assignments"
    assert plan.time_range == "next_7_days"
    assert plan.fields == ("due_date", "cutoff_date", "submission_status")
    assert plan.group_by == "course"
    assert client.request is not None
    assert client.request[1]["format"] == "json"
    assert "Databases" in client.request[1]["messages"][1]["content"]
    assert "course_query" in client.request[1]["messages"][0]["content"]


@pytest.mark.asyncio
async def test_ollama_planner_rejects_unknown_intent() -> None:
    client = FakeClient(FakeResponse('{"intent":"make_things_up"}'))

    with pytest.raises(RuntimeError, match="unknown query intent"):
        await OllamaQuestionPlanner(client=client).plan("Do something")


@pytest.mark.asyncio
async def test_ollama_planner_accepts_attendance_intent() -> None:
    client = FakeClient(
        FakeResponse(
            '{"intent":"attendance","time_range":"all",'
            '"direction":"all","fields":[],"group_by":null,'
            '"course_query":"DevOps Lab"}'
        )
    )

    plan = await OllamaQuestionPlanner(client=client).plan(
        "What is my attendance in DevOps Lab?"
    )

    assert plan.intent == "attendance"
    assert plan.course_query == "DevOps Lab"


@pytest.mark.asyncio
async def test_ollama_planner_accepts_attendance_history_intent() -> None:
    client = FakeClient(
        FakeResponse(
            '{"intent":"attendance","time_range":"all",'
            '"direction":"all","fields":[],"group_by":null,'
            '"course_query":"Compiler Construction Lab",'
            '"attendance_detail":"history","attendance_status":"absent"}'
        )
    )

    plan = await OllamaQuestionPlanner(client=client).plan(
        "Which classes did I miss in Compiler Construction Lab?"
    )

    assert plan.intent == "attendance"
    assert plan.attendance_detail == "history"
    assert plan.attendance_status == "absent"


@pytest.mark.asyncio
async def test_ollama_planner_accepts_overall_attendance_grouping() -> None:
    client = FakeClient(
        FakeResponse(
            '{"intent":"attendance","time_range":"all",'
            '"direction":"all","fields":[],"group_by":"overall",'
            '"course_query":null}'
        )
    )

    plan = await OllamaQuestionPlanner(client=client).plan(
        "What is my overall attendance?"
    )

    assert plan.intent == "attendance"
    assert plan.group_by == "overall"


def test_heuristic_planner_does_not_mistake_presentations_for_attendance() -> None:
    plan = heuristic_query_plan("Show the presentations for Compiler Construction")

    assert plan.intent == "documents"


def test_heuristic_planner_recognizes_missed_classes_as_attendance_history() -> None:
    plan = heuristic_query_plan(
        "Which classes did I miss in Compiler Construction Lab?",
        ("Compiler Construction Lab",),
    )

    assert plan.intent == "attendance"
    assert plan.attendance_detail == "history"
    assert plan.attendance_status == "absent"
    assert plan.course_query == "Compiler Construction Lab"
