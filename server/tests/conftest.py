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
