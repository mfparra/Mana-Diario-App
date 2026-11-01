"""Interface do adaptador LLM. O resto do servidor só conhece este módulo (e `get_llm_client`)."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LlmError(RuntimeError):
    """Falha ao gerar com a LLM (depois de esgotar as tentativas, quando aplicável)."""


class LlmUnavailable(LlmError):
    """Provedor fora do ar, timeout ou erro HTTP."""


class LlmContextOverflow(LlmError):
    """Prompt + saída não cabem no contexto configurado (falha cedo, sem chamar o provedor)."""


class LlmInvalidOutput(LlmError):
    """A resposta não virou um JSON válido no schema depois de todas as tentativas."""

    def __init__(self, message: str, last_error: str, raw: str, attempts: int = 0):
        super().__init__(message)
        self.last_error = last_error
        self.raw = raw
        self.attempts = attempts


@dataclass
class LlmUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class LlmResult[T: BaseModel]:
    data: T
    provider: str
    model: str
    attempts: int
    duration_s: float
    usage: LlmUsage = field(default_factory=LlmUsage)
    errors: list[str] = field(default_factory=list)  # erros de validação das tentativas anteriores


@dataclass
class LlmHealth:
    ok: bool
    provider: str
    model: str
    detail: str = ""


class LlmClient(Protocol):
    provider: str
    model: str

    async def generate_json(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        temperature: float | None = None,
        max_tokens: int | None = None,
        validate: Callable[[T], list[str]] | None = None,
    ) -> LlmResult[T]: ...

    async def health(self) -> LlmHealth: ...
