import re
import uuid
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import User
from app.db.session import get_session
from app.services.account import AccountService, effective_preferences

router = APIRouter(prefix="/me", tags=["me"])


class Preferences(BaseModel):
    notification_time: str
    notifications_enabled: bool
    timezone: str


class PreferencesPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notification_time: str | None = None
    notifications_enabled: bool | None = None
    timezone: str | None = None

    @field_validator("notification_time")
    @classmethod
    def _hhmm(cls, v: str | None) -> str | None:
        if v is not None and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", v):
            raise ValueError("use HH:MM (00:00–23:59)")
        return v

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str | None) -> str | None:
        if v is not None:
            try:
                ZoneInfo(v)
            except (ZoneInfoNotFoundError, ValueError):
                raise ValueError("fuso horário IANA inválido") from None
        return v


class MePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preferences: PreferencesPatch


class MeUser(BaseModel):
    id: uuid.UUID
    name: str | None
    email: str
    photo_url: str | None
    is_premium: bool


class SubscriptionSummary(BaseModel):
    is_premium: bool
    status: str | None = None
    expires_at: str | None = None


class MeOut(BaseModel):
    user: MeUser
    preferences: Preferences
    subscription: SubscriptionSummary


def _me(user: User, prefs: dict[str, Any]) -> MeOut:
    # Estado premium real vem da verificação de compra no servidor (Fase 8).
    return MeOut(
        user=MeUser(id=user.id, name=user.name, email=user.email, photo_url=user.photo_url, is_premium=False),
        preferences=Preferences(**prefs),
        subscription=SubscriptionSummary(is_premium=False),
    )


def get_account_service(session: AsyncSession = Depends(get_session)) -> AccountService:
    return AccountService(session)


@router.get("", response_model=MeOut)
async def get_me(user: User = Depends(get_current_user)) -> MeOut:
    return _me(user, effective_preferences(user))


@router.patch("", response_model=MeOut)
async def patch_me(
    body: MePatch, user: User = Depends(get_current_user), svc: AccountService = Depends(get_account_service)
) -> MeOut:
    changes = body.preferences.model_dump(exclude_none=True)
    prefs = await svc.update_preferences(user, changes) if changes else effective_preferences(user)
    return _me(user, prefs)


@router.delete("", status_code=202)
async def delete_me(
    user: User = Depends(get_current_user), svc: AccountService = Depends(get_account_service)
) -> Response:
    await svc.delete_account(user.id)
    return Response(status_code=202)


@router.get("/export")
async def export_me(
    user: User = Depends(get_current_user), svc: AccountService = Depends(get_account_service)
) -> JSONResponse:
    data = await svc.export(user)
    return JSONResponse(
        data, headers={"Content-Disposition": 'attachment; filename="mana-diario-meus-dados.json"'}
    )
