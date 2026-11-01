import httpx
import pytest

from app.api.v1.health import get_health_service
from app.core.config import Settings
from app.llm.health import check_llm
from app.main import create_app
from app.services.health import HealthService


def _service(db: str = "ok", llm: str = "ok", today: bool = True) -> HealthService:
    async def db_check():
        return db

    async def llm_check():
        return llm

    async def today_published():
        return today

    return HealthService(db_check, llm_check, today_published)


async def _get(service: HealthService) -> httpx.Response:
    app = create_app()
    app.dependency_overrides[get_health_service] = lambda: service
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        return await c.get("/v1/health")


async def test_health_ok():
    r = await _get(_service())
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "db": "ok", "llm": "ok", "today_published": True}


async def test_llm_fora_nao_derruba_api():
    r = await _get(_service(llm="degraded"))
    assert r.status_code == 200
    assert r.json()["llm"] == "degraded"


async def test_banco_fora_retorna_503():
    r = await _get(_service(db="error", today=True))
    assert r.status_code == 503
    assert r.json() == {"status": "error", "db": "error", "llm": "ok", "today_published": False}


async def test_health_padrao_sem_banco_configurado():
    app = create_app()
    from app.core.config import get_settings

    app.dependency_overrides[get_settings] = lambda: Settings(llm_provider="fake")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/v1/health")
    assert r.status_code == 200
    assert r.json()["db"] == "not_configured"


@pytest.mark.parametrize(("status", "esperado"), [(200, "ok"), (500, "degraded")])
async def test_check_llm(status, esperado):
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        seen["auth"] = req.headers.get("authorization")
        return httpx.Response(status, json={"data": []})

    s = Settings(llm_base_url="http://llm:8081/v1/", llm_api_key="k")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        assert await check_llm(s, c) == esperado
    assert seen == {"url": "http://llm:8081/v1/models", "auth": "Bearer k"}


async def test_check_llm_sem_conexao():
    def handler(req):
        raise httpx.ConnectError("recusado")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        assert await check_llm(Settings(), c) == "degraded"


def test_llm_extra_body_aceita_json_do_env(monkeypatch):
    monkeypatch.setenv("LLM_EXTRA_BODY", '{"chat_template_kwargs":{"enable_thinking":false}}')
    monkeypatch.setenv("LLM_API_KEY", "")
    s = Settings()
    assert s.llm_extra_body == {"chat_template_kwargs": {"enable_thinking": False}}
    assert s.llm_api_key is None
