import datetime as dt
import uuid

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.auth import get_google_verifier
from app.core.config import Settings, get_settings
from app.core.security import InvalidAccessToken, create_access_token, decode_access_token, hash_token
from app.db.models import RefreshToken, User
from app.db.session import get_session
from app.main import create_app
from app.services.google_id import GoogleIdTokenVerifier, InvalidGoogleToken
from tests.conftest import GOOGLE_CLIENT_ID, JWT_SECRET


@pytest.fixture
def verifier(google_keys):
    public = google_keys[0].public_key()
    return GoogleIdTokenVerifier(GOOGLE_CLIENT_ID, key_resolver=lambda token: public)


# --- verificação do ID token do Google (sem banco) ---------------------------------------------


async def test_token_valido(verifier, make_google_token):
    ident = await verifier.verify(make_google_token())
    assert (ident.sub, ident.email, ident.name) == ("google-sub-1", "fiel@exemplo.com", "Fiel Teste")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"forged": True},  # assinado por outra chave
        {"expires_in": -3600},  # expirado (além da tolerância de 60 s)
        {"aud": "outro-app.apps.googleusercontent.com"},  # aud errado
        {"iss": "https://atacante.example"},
        {"email_verified": False},
    ],
)
async def test_tokens_rejeitados(verifier, make_google_token, kwargs):
    with pytest.raises(InvalidGoogleToken):
        await verifier.verify(make_google_token(**kwargs))


async def test_token_malformado_e_alg_none(verifier):
    import jwt

    with pytest.raises(InvalidGoogleToken):
        await verifier.verify("nao.e.jwt")
    sem_assinatura = jwt.encode({"sub": "x", "aud": GOOGLE_CLIENT_ID}, None, algorithm="none")
    with pytest.raises(InvalidGoogleToken):
        await verifier.verify(sem_assinatura)


async def test_sem_client_id_configurado(google_keys, make_google_token):
    v = GoogleIdTokenVerifier(None, key_resolver=lambda t: google_keys[0].public_key())
    with pytest.raises(RuntimeError):
        await v.verify(make_google_token())


# --- tokens próprios -----------------------------------------------------------------------------


def test_access_token_ida_e_volta():
    uid = uuid.uuid4()
    claims = decode_access_token(create_access_token(uid, JWT_SECRET, 1800), JWT_SECRET)
    assert claims.user_id == uid


@pytest.mark.parametrize("caso", ["expirado", "outro_segredo", "lixo"])
def test_access_token_invalido(caso):
    uid = uuid.uuid4()
    if caso == "expirado":
        tok = create_access_token(uid, JWT_SECRET, 60, now=dt.datetime.now(dt.UTC) - dt.timedelta(hours=1))
    elif caso == "outro_segredo":
        tok = create_access_token(uid, "o" * 40, 60)
    else:
        tok = "abc.def.ghi"
    with pytest.raises(InvalidAccessToken):
        decode_access_token(tok, JWT_SECRET)


def test_segredo_curto_recusado():
    with pytest.raises(RuntimeError):
        create_access_token(uuid.uuid4(), "curto", 60)


# --- endpoint com banco real ---------------------------------------------------------------------


@pytest.fixture
async def api(migrated_db_url, verifier):
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def session_override():
        async with maker() as s:
            yield s

    app = create_app()
    settings = Settings(jwt_secret=JWT_SECRET, google_web_client_id=GOOGLE_CLIENT_ID, llm_provider="fake")
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_google_verifier] = lambda: verifier
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c, maker
    await engine.dispose()


async def test_login_cria_e_depois_atualiza_usuario(api, make_google_token):
    client, maker = api
    sub = f"sub-{uuid.uuid4()}"
    r = await client.post(
        "/v1/auth/google", json={"id_token": make_google_token(sub=sub), "device_label": "Pixel 8"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["created"] is True and body["user"]["is_premium"] is False
    assert body["access_expires_in"] == 1800 and body["refresh_expires_in"] == 5184000
    uid = uuid.UUID(body["user"]["id"])
    assert decode_access_token(body["access_token"], JWT_SECRET).user_id == uid

    r2 = await client.post(
        "/v1/auth/google", json={"id_token": make_google_token(sub=sub, email="novo@exemplo.com")}
    )
    assert r2.json()["user"]["created"] is False
    assert r2.json()["user"]["id"] == str(uid)

    async with maker() as s:
        user = await s.scalar(select(User).where(User.google_sub == sub))
        assert user.email == "novo@exemplo.com"
        tokens = (await s.scalars(select(RefreshToken).where(RefreshToken.user_id == uid))).all()
        assert len(tokens) == 2
        # banco guarda só o hash do refresh token
        assert {t.token_hash for t in tokens} == {
            hash_token(body["refresh_token"]),
            hash_token(r2.json()["refresh_token"]),
        }
        assert body["refresh_token"] not in {t.token_hash for t in tokens}
        assert tokens[0].device_label in ("Pixel 8", None)


@pytest.mark.parametrize("kwargs", [{"forged": True}, {"expires_in": -3600}, {"aud": "outro"}])
async def test_login_rejeita_tokens_invalidos(api, make_google_token, kwargs):
    client, _ = api
    r = await client.post("/v1/auth/google", json={"id_token": make_google_token(**kwargs)})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


async def test_login_valida_entrada(api):
    client, _ = api
    r = await client.post("/v1/auth/google", json={"id_token": "x"})
    assert r.status_code == 422


async def test_login_sem_client_id_configurado_responde_503(api, make_google_token):
    client, _ = api
    client_app = client._transport.app  # type: ignore[attr-defined]
    client_app.dependency_overrides[get_google_verifier] = lambda: GoogleIdTokenVerifier(None)
    r = await client.post("/v1/auth/google", json={"id_token": make_google_token()})
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "unavailable"
