"""Tokens próprios da API (DECISOES A2/A3).

- Access token: JWT HS256 assinado com `JWT_SECRET`, 30 min, `typ=access`.
- Refresh token: 32 bytes aleatórios (opaco); no banco só o SHA-256 (`refresh_tokens.token_hash`).
"""

import datetime as dt
import hashlib
import secrets
import uuid
from dataclasses import dataclass

import jwt

ISSUER = "mana-diario"
ALGORITHM = "HS256"


class InvalidAccessToken(Exception):
    pass


@dataclass(frozen=True)
class AccessClaims:
    user_id: uuid.UUID
    jti: str
    expires_at: dt.datetime


def _require_secret(secret: str | None) -> str:
    if not secret or len(secret) < 32:
        raise RuntimeError("JWT_SECRET ausente ou curto demais (mínimo 32 caracteres)")
    return secret


def create_access_token(
    user_id: uuid.UUID, secret: str | None, ttl_s: int, now: dt.datetime | None = None
) -> str:
    now = now or dt.datetime.now(dt.UTC)
    payload = {
        "iss": ISSUER,
        "sub": str(user_id),
        "typ": "access",
        "jti": uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int((now + dt.timedelta(seconds=ttl_s)).timestamp()),
    }
    return jwt.encode(payload, _require_secret(secret), algorithm=ALGORITHM)


def decode_access_token(token: str, secret: str | None) -> AccessClaims:
    try:
        claims = jwt.decode(
            token,
            _require_secret(secret),
            algorithms=[ALGORITHM],
            issuer=ISSUER,
            options={"require": ["exp", "iat", "sub", "jti"]},
        )
        if claims.get("typ") != "access":
            raise InvalidAccessToken("tipo de token incorreto")
        return AccessClaims(
            uuid.UUID(claims["sub"]), claims["jti"], dt.datetime.fromtimestamp(claims["exp"], dt.UTC)
        )
    except (jwt.PyJWTError, ValueError) as exc:
        raise InvalidAccessToken(type(exc).__name__) from exc


def new_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
