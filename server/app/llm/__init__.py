"""Adaptador LLM. Único lugar com particularidades de provedor/modelo.

Uso: `client = get_llm_client(settings)` → `await client.generate_json(system=..., user=..., schema=...)`.
"""

from app.core.config import Settings
from app.llm.base import (
    LlmClient,
    LlmContextOverflow,
    LlmError,
    LlmHealth,
    LlmInvalidOutput,
    LlmResult,
    LlmUnavailable,
)


def get_llm_client(settings: Settings) -> LlmClient:
    """Escolhe a implementação por `LLM_PROVIDER`. Novos provedores entram aqui como nova classe."""
    if settings.llm_provider == "openai_compatible":
        from app.llm.openai_compatible import OpenAICompatibleClient

        return OpenAICompatibleClient(settings)
    if settings.llm_provider == "fake":
        from app.llm.fake import FakeLlmClient

        return FakeLlmClient(model=settings.llm_model or "fake-model")
    raise ValueError(f"LLM_PROVIDER desconhecido: {settings.llm_provider}")


__all__ = [
    "LlmClient",
    "LlmContextOverflow",
    "LlmError",
    "LlmHealth",
    "LlmInvalidOutput",
    "LlmResult",
    "LlmUnavailable",
    "get_llm_client",
]
