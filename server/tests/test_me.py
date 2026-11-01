import datetime as dt
import uuid

import pytest
from sqlalchemy import text

from app.db.models import Base


async def test_get_me_com_preferencias_padrao(api_db, login):
    client, _ = api_db
    headers, body = await login()
    r = await client.get("/v1/me", headers=headers)
    assert r.status_code == 200
    me = r.json()
    assert me["user"]["id"] == body["user"]["id"]
    assert me["preferences"] == {
        "notification_time": "07:00", "notifications_enabled": True, "timezone": "America/Sao_Paulo",
    }  # fmt: skip
    assert me["subscription"] == {"is_premium": False, "status": None, "expires_at": None}


async def test_patch_preferencias(api_db, login):
    client, _ = api_db
    headers, _ = await login()
    r = await client.patch("/v1/me", headers=headers, json={"preferences": {"notification_time": "06:30"}})
    assert r.status_code == 200
    assert r.json()["preferences"]["notification_time"] == "06:30"
    r = await client.patch("/v1/me", headers=headers, json={"preferences": {"timezone": "Europe/Lisbon"}})
    prefs = (await client.get("/v1/me", headers=headers)).json()["preferences"]
    assert (prefs["notification_time"], prefs["timezone"]) == ("06:30", "Europe/Lisbon")


@pytest.mark.parametrize(
    "prefs",
    [
        {"notification_time": "25:00"},
        {"notification_time": "7h"},
        {"timezone": "Marte/Base"},
        {"cor": "azul"},
    ],
)
async def test_patch_invalido(api_db, login, prefs):
    client, _ = api_db
    headers, _ = await login()
    r = await client.patch("/v1/me", headers=headers, json={"preferences": prefs})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


async def test_sem_autenticacao(api_db):
    client, _ = api_db
    for method, path in (
        ("GET", "/v1/me"),
        ("PATCH", "/v1/me"),
        ("DELETE", "/v1/me"),
        ("GET", "/v1/me/export"),
    ):
        assert (await client.request(method, path)).status_code == 401


async def test_export(api_db, login):
    client, _ = api_db
    headers, body = await login()
    r = await client.get("/v1/me/export", headers=headers)
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    data = r.json()
    assert data["user"]["email"] == "fiel@exemplo.com"
    assert set(data) >= {
        "user",
        "preferences",
        "sessions",
        "subscriptions",
        "notes",
        "profile",
        "personal_studies",
    }
    assert len(data["sessions"]) == 1
    assert body["refresh_token"] not in r.text  # nunca exporta segredos de sessão


async def test_excluir_conta_apaga_todas_as_tabelas_relacionadas(api_db, login):
    client, maker = api_db
    headers, body = await login()
    uid = uuid.UUID(body["user"]["id"])
    agora = dt.datetime.now(dt.UTC)
    async with maker() as s:  # dados em todas as tabelas com user_id
        await s.execute(
            text("INSERT INTO notes (user_id, date, encrypted_body) VALUES (:u, '2026-11-01', '\\\\x01')"),
            {"u": uid},
        )
        await s.execute(
            text(
                "INSERT INTO user_profiles (user_id, encrypted_payload, consent_at, consent_version) "
                "VALUES (:u, '\\\\x02', :a, 'v1')"
            ),
            {"u": uid, "a": agora},
        )
        await s.execute(
            text("INSERT INTO personal_studies (user_id, date, payload) VALUES (:u, '2026-11-01', '{}')"),
            {"u": uid},
        )
        await s.execute(
            text(
                "INSERT INTO subscriptions (user_id, product_id, purchase_token_hash, status) "
                "VALUES (:u, 'p', :h, 'active')"
            ),
            {"u": uid, "h": f"h-{uid}"},
        )
        await s.execute(
            text("INSERT INTO generation_jobs (kind, date, user_id) VALUES ('personal', '2026-11-01', :u)"),
            {"u": uid},
        )
        await s.commit()

    r = await client.delete("/v1/me", headers=headers)
    assert r.status_code == 202

    tabelas_com_usuario = [t.name for t in Base.metadata.sorted_tables if "user_id" in t.c]
    assert set(tabelas_com_usuario) >= {"notes", "user_profiles", "personal_studies", "subscriptions",
                                        "generation_jobs", "refresh_tokens"}  # fmt: skip
    async with maker() as s:
        assert (await s.execute(text("SELECT count(*) FROM users WHERE id = :u"), {"u": uid})).scalar() == 0
        for tabela in tabelas_com_usuario:
            n = (
                await s.execute(text(f"SELECT count(*) FROM {tabela} WHERE user_id = :u"), {"u": uid})
            ).scalar()
            assert n == 0, tabela
    # o access token antigo deixa de valer e o refresh também
    assert (await client.get("/v1/me", headers=headers)).status_code == 401
    assert (
        await client.post("/v1/auth/refresh", json={"refresh_token": body["refresh_token"]})
    ).status_code == 401


def test_lista_de_tabelas_do_usuario_esta_completa():
    from app.services.account import USER_TABLES

    com_user_id = {t.name for t in Base.metadata.sorted_tables if "user_id" in t.c}
    assert {m.__tablename__ for m in USER_TABLES} == com_user_id
