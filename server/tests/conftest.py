"""Fixtures compartilhadas: banco real (TEST_DATABASE_URL) e chaves RSA para simular o Google."""

import datetime as dt
import os
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

SERVER = Path(__file__).resolve().parents[1]
DB_URL = os.environ.get("TEST_DATABASE_URL")
requires_db = pytest.mark.skipif(not DB_URL, reason="TEST_DATABASE_URL não definida (scripts/test-db.sh up)")

GOOGLE_CLIENT_ID = "teste-web-client.apps.googleusercontent.com"
JWT_SECRET = "s" * 40
FIELD_KEY = "1:" + "A" * 43  # 32 bytes zerados em base64url (só para testes)


@pytest.fixture(scope="session")
def migrated_db_url():
    """Banco limpo com todas as migrações aplicadas (uma vez por sessão de testes)."""
    if not DB_URL:
        pytest.skip("TEST_DATABASE_URL não definida")
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text

    eng = create_engine(DB_URL)
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    eng.dispose()
    cfg = Config(str(SERVER / "alembic.ini"))
    cfg.set_main_option("script_location", str(SERVER / "migrations"))
    cfg.set_main_option("sqlalchemy.url", DB_URL)
    cfg.attributes["skip_logging"] = True
    command.upgrade(cfg, "head")
    return DB_URL


@pytest.fixture(scope="session")
def google_keys():
    """Par de chaves que faz o papel das chaves do Google; e outro par 'de atacante'."""
    return (
        rsa.generate_private_key(public_exponent=65537, key_size=2048),
        rsa.generate_private_key(public_exponent=65537, key_size=2048),
    )


@pytest.fixture
def make_google_token(google_keys):
    def make(
        sub: str = "google-sub-1",
        email: str = "fiel@exemplo.com",
        aud: str = GOOGLE_CLIENT_ID,
        iss: str = "https://accounts.google.com",
        expires_in: int = 3600,
        email_verified: bool = True,
        forged: bool = False,
        **extra,
    ) -> str:
        now = dt.datetime.now(dt.UTC)
        claims = {
            "iss": iss, "aud": aud, "sub": sub, "email": email, "email_verified": email_verified,
            "name": "Fiel Teste", "picture": "https://exemplo.com/foto.png",
            "iat": int(now.timestamp()) - 10,
            "exp": int((now + dt.timedelta(seconds=expires_in)).timestamp()),
            **extra,
        }  # fmt: skip
        key = google_keys[1] if forged else google_keys[0]
        return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "k1"})

    return make


@pytest.fixture
async def api_db(migrated_db_url, google_keys):
    """(cliente HTTP, sessionmaker) com banco real, Google simulado e LLM falsa."""
    import httpx
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.api.v1.auth import get_google_verifier
    from app.core.config import Settings, get_settings
    from app.core.crypto import FieldCipher, get_cipher
    from app.db.session import get_session
    from app.main import create_app
    from app.services.google_id import GoogleIdTokenVerifier

    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def session_override():
        async with maker() as s:
            yield s

    app = create_app()
    public = google_keys[0].public_key()
    settings = Settings(jwt_secret=JWT_SECRET, google_web_client_id=GOOGLE_CLIENT_ID, llm_provider="fake")
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_google_verifier] = lambda: GoogleIdTokenVerifier(
        GOOGLE_CLIENT_ID, lambda t: public
    )
    app.dependency_overrides[get_cipher] = lambda: FieldCipher(FIELD_KEY)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        c.app = app
        yield c, maker
    await engine.dispose()


@pytest.fixture
def login(api_db, make_google_token):
    """Faz login de um usuário novo e devolve (headers de auth, corpo do login)."""
    import uuid

    async def do(sub: str | None = None):
        client, _ = api_db
        r = await client.post(
            "/v1/auth/google", json={"id_token": make_google_token(sub=sub or f"s-{uuid.uuid4()}")}
        )
        assert r.status_code == 200, r.text
        body = r.json()
        return {"Authorization": f"Bearer {body['access_token']}"}, body

    return do
