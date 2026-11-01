"""LLM falsa para testes: devolve respostas gravadas em sequência e registra as chamadas."""

from collections.abc import Iterable

from pydantic import BaseModel

from app.llm.base import LlmHealth, LlmResult, LlmUsage
from app.llm.generation import CompletionOut, generate_with_retries


class FakeLlmClient:
    provider = "fake"

    def __init__(
        self,
        responses: Iterable[str | Exception] = (),
        model: str = "fake-model",
        max_attempts: int = 3,
        healthy: bool = True,
    ):
        self.responses = list(responses)
        self.model = model
        self.max_attempts = max_attempts
        self.healthy = healthy
        self.calls: list[list[dict[str, str]]] = []

    async def generate_json[T: BaseModel](
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LlmResult[T]:
        async def complete(messages: list[dict[str, str]]) -> CompletionOut:
            self.calls.append(messages)
            if not self.responses:
                raise AssertionError("FakeLlmClient sem respostas gravadas")
            r = self.responses.pop(0)
            if isinstance(r, Exception):
                raise r
            return CompletionOut(r, LlmUsage(len(system + user) // 4, len(r) // 4))

        return await generate_with_retries(
            complete,
            system=system,
            user=user,
            schema=schema,
            max_attempts=self.max_attempts,
            strip_thinking=True,
            provider=self.provider,
            model=self.model,
        )

    async def health(self) -> LlmHealth:
        return LlmHealth(self.healthy, self.provider, self.model)
