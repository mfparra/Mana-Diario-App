import logging
import uuid

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.core.ratelimit import AUTH, limit_by_ip
from app.db.session import get_session
from app.services.auth import AuthService, InvalidRefreshToken
from app.services.google_id import GoogleIdTokenVerifier, GoogleLoginNotConfigured, InvalidGoogleToken

log = logging.getLogger("app.auth")
router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(limit_by_ip(AUTH))])


class GoogleLoginIn(BaseModel):
    id_token: str = Field(min_length=20, max_length=4096)
    device_label: str | None = Field(default=None, max_length=100)


class UserOut(BaseModel):
    id: uuid.UUID
    name: str | None
    email: str
    photo_url: str | None
    is_premium: bool
    created: bool


class LoginOut(BaseModel):
    access_token: str
    access_expires_in: int
    refresh_token: str
    refresh_expires_in: int
    user: UserOut


def get_google_verifier(settings: Settings = Depends(get_settings)) -> GoogleIdTokenVerifier:
    return GoogleIdTokenVerifier(settings.google_web_client_id)


def get_auth_service(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    verifier: GoogleIdTokenVerifier = Depends(get_google_verifier),
) -> AuthService:
    return AuthService(session, settings, verifier)


def _unauthorized() -> ApiError:
    return ApiError("unauthorized", "Login com Google inválido ou expirado. Entre novamente.", 401)


@router.post("/google", response_model=LoginOut)
async def login_google(body: GoogleLoginIn, service: AuthService = Depends(get_auth_service)) -> LoginOut:
    try:
        result = await service.login_google(body.id_token, body.device_label)
    except InvalidGoogleToken:
        raise _unauthorized() from None
    except GoogleLoginNotConfigured:
        log.error("login Google indisponível: GOOGLE_WEB_CLIENT_ID não configurado")
        raise ApiError("unavailable", "Login temporariamente indisponível.", 503) from None
    t, u = result.tokens, result.user
    return LoginOut(
        access_token=t.access_token,
        access_expires_in=t.access_expires_in,
        refresh_token=t.refresh_token,
        refresh_expires_in=t.refresh_expires_in,
        # is_premium vem da verificação de assinatura no servidor (Fase 8); até lá, sempre falso
        user=UserOut(
            id=u.id,
            name=u.name,
            email=u.email,
            photo_url=u.photo_url,
            is_premium=False,
            created=result.created,
        ),
    )


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=200)


class TokensOut(BaseModel):
    access_token: str
    access_expires_in: int
    refresh_token: str
    refresh_expires_in: int


@router.post("/refresh", response_model=TokensOut)
async def refresh(body: RefreshIn, service: AuthService = Depends(get_auth_service)) -> TokensOut:
    try:
        t = await service.refresh(body.refresh_token)
    except InvalidRefreshToken:
        raise ApiError("unauthorized", "Sessão expirada. Entre novamente.", 401) from None
    return TokensOut(
        access_token=t.access_token,
        access_expires_in=t.access_expires_in,
        refresh_token=t.refresh_token,
        refresh_expires_in=t.refresh_expires_in,
    )


@router.post("/logout", status_code=204)
async def logout(body: RefreshIn, service: AuthService = Depends(get_auth_service)) -> Response:
    await service.logout(body.refresh_token)
    return Response(status_code=204)
