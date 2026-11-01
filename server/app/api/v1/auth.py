import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.db.session import get_session
from app.services.auth import AuthService
from app.services.google_id import GoogleIdTokenVerifier, InvalidGoogleToken

router = APIRouter(prefix="/auth", tags=["auth"])


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
