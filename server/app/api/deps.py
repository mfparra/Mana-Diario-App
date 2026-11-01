"""Dependências comuns dos routers: usuário autenticado."""

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.core.security import InvalidAccessToken, decode_access_token
from app.db.models import User
from app.db.session import get_session


def _unauthorized() -> ApiError:
    return ApiError("unauthorized", "Autenticação necessária.", 401, headers={"WWW-Authenticate": "Bearer"})


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> User:
    auth = request.headers.get("authorization", "")
    scheme, _, token = auth.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _unauthorized()
    try:
        claims = decode_access_token(token.strip(), settings.jwt_secret)
    except InvalidAccessToken:
        raise _unauthorized() from None
    user = await session.get(User, claims.user_id)
    if user is None or user.deleted_at is not None:
        raise _unauthorized()
    return user
