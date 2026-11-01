import datetime as dt
import json

import pytest
from sqlalchemy import text

from app.core.config import Settings, get_settings
from tests.conftest import GOOGLE_CLIENT_ID, JWT_SECRET

TOKEN = "admin-" + "x" * 30


@pytest.fixture
async def admin(api_db):
    client, maker = api_db
    client.app.dependency_overrides[get_settings] = lambda: Settings(
        jwt_secret=JWT_SECRET, google_web_client_id=GOOGLE_CLIENT_ID, llm_provider="fake", admin_token=TOKEN
    )
    async with maker() as s:
        await s.execute(text("DELETE FROM studies"))
        await s.execute(text("DELETE FROM generation_jobs"))
        for d, st, payload in [
            ("2026-11-01", "published", {"title": "PAZ"}),
            ("2026-11-02", "failed", None),
            ("2026-11-03", "draft", {"title": "FÉ"}),
        ]:
            await s.execute(
                text(
                    "INSERT INTO studies (date, status, payload, verse_ref) "
                    "VALUES (:d, :s, CAST(:p AS jsonb), 'JHN 3:16')"
                ),
                {"d": dt.date.fromisoformat(d), "s": st, "p": json.dumps(payload) if payload else None},
            )
        erro = "LlmInvalidOutput: resposta inválida"
        await s.execute(
            text(
                "INSERT INTO generation_jobs (kind, date, status, last_error) VALUES ('daily', '2026-11-02', 'failed', :e)"
            ),
            {"e": erro},
        )
        await s.commit()
    return client, maker, {"X-Admin-Token": TOKEN}


@pytest.mark.parametrize("headers", [{}, {"X-Admin-Token": "errado"}])
async def test_sem_token_valido_e_negado(admin, headers):
    client, _, _ = admin
    r = await client.get("/v1/admin/studies", headers=headers)
    assert r.status_code == 403


async def test_desativado_sem_admin_token_configurado(api_db):
    client, _ = api_db
    r = await client.get("/v1/admin/studies", headers={"X-Admin-Token": "qualquer"})
    assert r.status_code == 503


async def test_listar_falhas(admin):
    client, _, h = admin
    r = await client.get("/v1/admin/studies", params={"status": "failed"}, headers=h)
    items = r.json()["items"]
    assert [i["date"] for i in items] == ["2026-11-02"]
    assert items[0]["last_error"].startswith("LlmInvalidOutput")
    assert len((await client.get("/v1/admin/studies", headers=h)).json()["items"]) == 3


async def test_regenerar_enfileira_job_unico(admin):
    client, maker, h = admin
    r1 = await client.post("/v1/admin/studies/2026-11-02/regenerate", headers=h)
    r2 = await client.post("/v1/admin/studies/2026-11-02/regenerate", headers=h)
    assert r1.status_code == 202 and r1.json()["status"] == "pending"
    assert r1.json()["job_id"] == r2.json()["job_id"]  # não duplica
    async with maker() as s:
        n = (await s.execute(text("SELECT count(*) FROM generation_jobs WHERE status = 'pending'"))).scalar()
        assert n == 1


async def test_publicar_e_despublicar(admin):
    client, _, h = admin
    assert (
        await client.post("/v1/admin/studies/2026-11-02/publish", headers=h)
    ).status_code == 409  # sem conteúdo
    r = await client.post("/v1/admin/studies/2026-11-03/publish", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "published"
    r = await client.post("/v1/admin/studies/2026-11-01/unpublish", headers=h)
    assert r.json()["status"] == "draft"
    assert (await client.post("/v1/admin/studies/2020-01-01/publish", headers=h)).status_code == 404
