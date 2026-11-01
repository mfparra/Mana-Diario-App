import json
import logging

import httpx
import pytest
from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.core.logging import JsonFormatter
from app.main import create_app

router = APIRouter(prefix="/v1/_teste")


class Entrada(BaseModel):
    email: str
    idade: int


@router.get("/api-error")
async def api_error():
    raise ApiError("study_not_available", "Estudo ainda não disponível.", 404, {"date": "2026-11-01"})


@router.post("/validacao")
async def validacao(body: Entrada):
    return body


@router.get("/explode")
async def explode():
    dado_do_usuario = "fulano" + "@exemplo.com"  # montado em tempo de execução, como dado real
    raise RuntimeError(f"segredo do usuário: {dado_do_usuario}")


@router.get("/item/{item_id}")
async def item(item_id: int):
    return {"id": item_id}


@pytest.fixture
async def client():
    app = create_app()
    app.include_router(router)
    app.dependency_overrides[get_settings] = lambda: Settings(llm_provider="fake")  # health sem rede
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        yield c


@pytest.fixture
def logs():
    """Captura as linhas JSON emitidas pelo formatter real."""
    lines: list[dict] = []

    class H(logging.Handler):
        def emit(self, record):
            lines.append(json.loads(JsonFormatter().format(record)))

    h = H()
    logging.getLogger().addHandler(h)
    yield lines
    logging.getLogger().removeHandler(h)


async def test_api_error_no_formato_padrao(client):
    r = await client.get("/v1/_teste/api-error")
    assert r.status_code == 404
    assert r.json() == {
        "error": {"code": "study_not_available", "message": "Estudo ainda não disponível.",
                  "details": {"date": "2026-11-01"}}
    }  # fmt: skip


async def test_404_de_rota_inexistente(client):
    r = await client.get("/v1/nao-existe")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


async def test_405(client):
    r = await client.delete("/v1/health")
    assert r.status_code == 405
    assert r.json()["error"]["code"] == "method_not_allowed"


async def test_validacao_nao_ecoa_valores(client):
    r = await client.post("/v1/_teste/validacao", json={"email": "fulano@exemplo.com", "idade": "x"})
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["details"]["fields"] == [{"loc": ["body", "idade"], "type": "int_parsing"}]
    assert "fulano" not in r.text and '"x"' not in r.text


async def test_erro_nao_tratado_vira_500_sem_vazar(client, logs):
    r = await client.get("/v1/_teste/explode", headers={"X-Request-ID": "teste-req-123"})
    assert r.status_code == 500
    erro_500 = {
        "code": "internal_error",
        "message": "Erro interno. Tente novamente mais tarde.",
        "details": {},
    }
    assert r.json() == {"error": erro_500}
    assert r.headers["x-request-id"] == "teste-req-123"
    assert "fulano" not in r.text
    erro = next(line for line in logs if line["msg"] == "erro não tratado")
    assert erro["request_id"] == "teste-req-123"
    assert erro["exc_type"] == "RuntimeError"
    assert all("fulano" not in json.dumps(line) for line in logs)


async def test_request_id_gerado_ou_propagado(client):
    r = await client.get("/v1/_teste/item/1")
    assert len(r.headers["x-request-id"]) == 32
    r = await client.get("/v1/_teste/item/1", headers={"X-Request-ID": "abcdef12-cliente"})
    assert r.headers["x-request-id"] == "abcdef12-cliente"
    r = await client.get("/v1/_teste/item/1", headers={"X-Request-ID": "<script>"})
    assert r.headers["x-request-id"] != "<script>"


async def test_log_de_acesso_sem_pii(client, logs):
    await client.get("/v1/_teste/item/42?email=fulano@exemplo.com", headers={"Authorization": "Bearer xyz"})
    acesso = [line for line in logs if line["logger"] == "app.access"]
    assert len(acesso) == 1
    a = acesso[0]
    assert a["route"] == "/v1/_teste/item/{item_id}"  # modelo da rota, não o valor
    assert (a["method"], a["status"]) == ("GET", 200)
    assert {"request_id", "duration_ms"} <= a.keys()
    texto = json.dumps(acesso)
    assert "fulano" not in texto and "xyz" not in texto and "client" not in texto
    assert "/42" not in texto


def test_extra_fora_da_lista_e_descartado():
    rec = logging.LogRecord("x", logging.INFO, __file__, 1, "msg", None, None)
    rec.email = "fulano@exemplo.com"
    rec.model = "m"
    out = json.loads(JsonFormatter().format(rec))
    assert "email" not in out and out["model"] == "m"


async def test_cors_desligado(client):
    r = await client.options(
        "/v1/health", headers={"Origin": "https://malicioso.example", "Access-Control-Request-Method": "GET"}
    )
    assert not any(h.lower().startswith("access-control-") for h in r.headers)
    r = await client.get("/v1/health", headers={"Origin": "https://malicioso.example"})
    assert "access-control-allow-origin" not in r.headers


async def test_rota_inexistente_nao_registra_caminho(client, logs):
    await client.get("/v1/fulano@exemplo.com")
    acesso = [line for line in logs if line["logger"] == "app.access"]
    assert acesso[0]["route"] == "<sem rota>"
