import pytest

from tracy.adapters.llm.ollama import OllamaAnswerComposer


class FakeResponse:
    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return {"message": {"content": "Grounded local answer [1]"}}


class FakeClient:
    def __init__(self) -> None:
        self.request: tuple[str, dict] | None = None

    async def post(self, path: str, *, json: dict) -> FakeResponse:
        self.request = (path, json)
        return FakeResponse()


@pytest.mark.asyncio
async def test_ollama_composer_sends_grounding_context_to_local_chat_api() -> None:
    client = FakeClient()
    composer = OllamaAnswerComposer(model="test-model", client=client)

    answer = await composer.compose("What is this?", "[1] Course Syllabus")

    assert answer == "Grounded local answer [1]"
    assert client.request is not None
