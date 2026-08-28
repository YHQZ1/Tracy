import pytest

from tracy.adapters.llm.planner import OllamaQuestionPlanner


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
