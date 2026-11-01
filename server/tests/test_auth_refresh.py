"""Refresh rotativo, logout e detecção de reuso (PLANO 4.2). Banco real."""

import datetime as dt
import uuid

import httpx
import pytest
from fastapi import Depends
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import get_current_user
from app.api.v1.auth import get_google_verifier
from app.core.config import Settings, get_settings
from app.core.security import hash_token
from app.db.models import RefreshToken, User
from app.db.session import get_session
from app.main import create_app
from app.services.google_id import GoogleIdTokenVerifier
from tests.conftest import GOOGLE_CLIENT_ID, JWT_SECRET


@pytest.fixture
async def api(migrated_db_url, google_keys):
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def session_override():
        async with maker() as s:
            yield s

    app = create_app()

    @app.get("/v1/_teste/eu")
    async def eu(user: User = Depends(get_current_user)):
        return {"id": str(user.id)}

    public = google_keys[0].public_key()
    settings = Settings(jwt_secret=JWT_SECRET, google_web_client_id=GOOGLE_CLIENT_ID, llm_provider="fake")
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_google_verifier] = lambda: GoogleIdTokenVerifier(
        GOOGLE_CLIENT_ID, lambda t: public
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c, maker
    await engine.dispose()


async def _login(client, make_google_token, sub=None) -> dict:
    r = await client.post(
        "/v1/auth/google", json={"id_token": make_google_token(sub=sub or f"s-{uuid.uuid4()}")}
    )
    assert r.status_code == 200
    return r.json()


async def _refresh(client, token: str) -> httpx.Response:
    return await client.post("/v1/auth/refresh", json={"refresh_token": token})


async def _envelhecer(maker, token: str, segundos: int = 60) -> None:
    """Simula que a rotação aconteceu há `segundos` (sai da janela de tolerância)."""
    async with maker() as s:
        await s.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == hash_token(token))
            .values(revoked_at=dt.datetime.now(dt.UTC) - dt.timedelta(seconds=segundos))
        )
        await s.commit()


async def test_rotacao(api, make_google_token):
    client, maker = api
    login = await _login(client, make_google_token)
    r = await _refresh(client, login["refresh_token"])
    assert r.status_code == 200
    novo = r.json()
    assert novo["refresh_token"] != login["refresh_token"]
    assert (
        await client.get("/v1/_teste/eu", headers={"Authorization": f"Bearer {novo['access_token']}"})
    ).status_code == 200
    async with maker() as s:
        antigo = await s.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == hash_token(login["refresh_token"]))
        )
        atual = await s.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == hash_token(novo["refresh_token"]))
        )
        assert antigo.revoked_at is not None and antigo.replaced_by_id == atual.id
        assert atual.family_id == antigo.family_id and atual.revoked_at is None
    # o novo também rotaciona
    assert (await _refresh(client, novo["refresh_token"])).status_code == 200


async def test_reuso_revoga_todas_as_sessoes_do_usuario(api, make_google_token):
    client, maker = api
    sub = f"s-{uuid.uuid4()}"
    aparelho1 = await _login(client, make_google_token, sub)
    aparelho2 = await _login(client, make_google_token, sub)
    r1 = (await _refresh(client, aparelho1["refresh_token"])).json()
    await _envelhecer(maker, aparelho1["refresh_token"])

    # alguém reapresenta o refresh antigo (roubado) → 401 e todas as sessões caem
    r = await _refresh(client, aparelho1["refresh_token"])
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"
    assert (await _refresh(client, r1["refresh_token"])).status_code == 401
    assert (await _refresh(client, aparelho2["refresh_token"])).status_code == 401


async def test_repeticao_imediata_nao_derruba_outras_sessoes(api, make_google_token):
    client, _ = api
    login = await _login(client, make_google_token)
    novo = (await _refresh(client, login["refresh_token"])).json()
    # o app reenviou o mesmo pedido por falha de rede (dentro da janela de tolerância)
    assert (await _refresh(client, login["refresh_token"])).status_code == 401
    assert (await _refresh(client, novo["refresh_token"])).status_code == 200


async def test_refresh_expirado_ou_desconhecido(api, make_google_token):
    client, maker = api
    login = await _login(client, make_google_token)
    async with maker() as s:
        await s.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == hash_token(login["refresh_token"]))
            .values(expires_at=dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1))
        )
        await s.commit()
    assert (await _refresh(client, login["refresh_token"])).status_code == 401
    assert (await _refresh(client, "x" * 43)).status_code == 401


async def test_logout(api, make_google_token):
    client, _ = api
    sub = f"s-{uuid.uuid4()}"
    a = await _login(client, make_google_token, sub)
    b = await _login(client, make_google_token, sub)
    r = await client.post("/v1/auth/logout", json={"refresh_token": a["refresh_token"]})
    assert r.status_code == 204
    assert (await _refresh(client, a["refresh_token"])).status_code == 401
    assert (await _refresh(client, b["refresh_token"])).status_code == 200  # outro aparelho continua
    # idempotente, inclusive com token desconhecido
    assert (
        await client.post("/v1/auth/logout", json={"refresh_token": a["refresh_token"]})
    ).status_code == 204
    assert (await client.post("/v1/auth/logout", json={"refresh_token": "y" * 43})).status_code == 204


@pytest.mark.parametrize("header", [None, "Bearer", "Basic abc", "Bearer lixo.lixo.lixo"])
async def test_endpoint_protegido_sem_token_valido(api, header):
    client, _ = api
    headers = {"Authorization": header} if header else {}
    r = await client.get("/v1/_teste/eu", headers=headers)
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"
