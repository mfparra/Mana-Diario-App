"""Verificação de disponibilidade do provedor LLM para o `/v1/health`."""

import httpx

from app.core.config import Settings


async def check_llm(settings: Settings, client: httpx.AsyncClient | None = None) -> str:
    """'ok' se o provedor responde e serve o modelo configurado; 'degraded' caso contrário."""
    if settings.llm_provider == "fake":
        return "ok"
    from app.llm.openai_compatible import OpenAICompatibleClient

    try:
        health = await OpenAICompatibleClient(settings, http=client).health()
    except ValueError:  # LLM_MODEL ausente
        return "degraded"
    return "ok" if health.ok else "degraded"
