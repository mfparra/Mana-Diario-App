"""Validação do ID token do Google (login pelo Credential Manager no app).

Confere assinatura RS256 com as chaves públicas do Google (JWKS, em cache), `aud` = Web client ID
(`GOOGLE_WEB_CLIENT_ID`), `iss`, `exp`/`iat` e `email_verified`.
"""

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import anyio
import jwt

GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = ("accounts.google.com", "https://accounts.google.com")
LEEWAY_S = 60  # tolerância de relógio


class InvalidGoogleToken(Exception):
    pass


class GoogleLoginNotConfigured(RuntimeError):
    """GOOGLE_WEB_CLIENT_ID ausente (configuração do servidor, não erro do usuário)."""


@dataclass(frozen=True)
class GoogleIdentity:
    sub: str
    email: str
    name: str | None
    photo_url: str | None


KeyResolver = Callable[[str], Any]  # token → chave pública


@lru_cache
def _jwks_client() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(GOOGLE_JWKS_URL, cache_keys=True, lifespan=3600, timeout=10)


def _google_key(token: str) -> Any:
    return _jwks_client().get_signing_key_from_jwt(token).key


class GoogleIdTokenVerifier:
    def __init__(self, client_id: str | None, key_resolver: KeyResolver = _google_key):
        self.client_id = client_id
        self._resolve = key_resolver

    def _verify_sync(self, token: str) -> GoogleIdentity:
        if not self.client_id:
            raise GoogleLoginNotConfigured("GOOGLE_WEB_CLIENT_ID não configurado")
        try:
            key = self._resolve(token)
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience=self.client_id,
                leeway=LEEWAY_S,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise InvalidGoogleToken(type(exc).__name__) from exc
        if claims.get("iss") not in GOOGLE_ISSUERS:
            raise InvalidGoogleToken("emissor inválido")
        if claims.get("email_verified") is not True or not claims.get("email"):
            raise InvalidGoogleToken("e-mail não verificado")
        return GoogleIdentity(
            sub=str(claims["sub"]),
            email=str(claims["email"]),
            name=claims.get("name"),
            photo_url=claims.get("picture"),
        )

    async def verify(self, token: str) -> GoogleIdentity:
        # PyJWKClient faz HTTP síncrono (com cache); roda fora do event loop
        return await anyio.to_thread.run_sync(self._verify_sync, token)
