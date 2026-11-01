"""Verificação de disponibilidade do servidor LLM (API compatível com OpenAI: `GET /models`)."""

import httpx

from app.core.config import Settings


async def check_llm(settings: Settings, client: httpx.AsyncClient | None = None) -> str:
    """'ok' se o provedor responde; 'degraded' caso contrário. Nunca levanta exceção."""
    if settings.llm_provider == "fake":
        return "ok"
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"} if settings.llm_api_key else {}
    url = settings.llm_base_url.rstrip("/") + "/models"
    try:
        if client is None:
            async with httpx.AsyncClient(timeout=settings.llm_health_timeout_s) as c:
                resp = await c.get(url, headers=headers)
        else:
            resp = await client.get(url, headers=headers, timeout=settings.llm_health_timeout_s)
        return "ok" if resp.status_code == 200 else "degraded"
    except httpx.HTTPError:
        return "degraded"
