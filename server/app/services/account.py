"""Conta do usuário: preferências, exclusão (LGPD) e exportação de dados."""

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import FieldCipher
from app.db.models import (
    GenerationJob,
    Note,
    PersonalStudy,
    RefreshToken,
    Subscription,
    User,
    UserProfile,
)
from app.notes.service import NotesService

DEFAULT_PREFERENCES: dict[str, Any] = {
    "notification_time": "07:00",
    "notifications_enabled": True,
    "timezone": "America/Sao_Paulo",
}

# Tabelas com dados do usuário. Toda tabela nova com `user_id` precisa entrar aqui
# (o teste de exclusão confere contra o metadata).
USER_TABLES = (RefreshToken, Note, UserProfile, PersonalStudy, Subscription, GenerationJob)


def effective_preferences(user: User) -> dict[str, Any]:
    return {**DEFAULT_PREFERENCES, **(user.preferences or {})}


def _iso(v: Any) -> Any:
    return v.isoformat() if isinstance(v, dt.date | dt.datetime) else v


class AccountService:
    def __init__(self, session: AsyncSession, cipher: FieldCipher):
        self.session = session
        self.cipher = cipher

    async def update_preferences(self, user: User, changes: dict[str, Any]) -> dict[str, Any]:
        user.preferences = {**(user.preferences or {}), **changes}
        user.updated_at = dt.datetime.now(dt.UTC)
        await self.session.commit()
        return effective_preferences(user)

    async def delete_account(self, user_id: uuid.UUID) -> None:
        """Apaga o usuário e, por `ON DELETE CASCADE`, todos os dados dele. Imediato e irreversível."""
        await self.session.execute(delete(User).where(User.id == user_id))
        await self.session.commit()

    async def export(self, user: User) -> dict[str, Any]:
        """Todos os dados do usuário em JSON (LGPD, direito de acesso/portabilidade)."""
        sessions = (
            await self.session.scalars(select(RefreshToken).where(RefreshToken.user_id == user.id))
        ).all()
        subs = (await self.session.scalars(select(Subscription).where(Subscription.user_id == user.id))).all()
        personal = (
            await self.session.scalars(select(PersonalStudy).where(PersonalStudy.user_id == user.id))
        ).all()
        profile = await self.session.get(UserProfile, user.id)
        return {
            "exported_at": dt.datetime.now(dt.UTC).isoformat(),
            "user": {
                "id": str(user.id),
                "email": user.email,
                "name": user.name,
                "photo_url": user.photo_url,
                "created_at": _iso(user.created_at),
            },
            "preferences": effective_preferences(user),
            "sessions": [
                {
                    "device_label": s.device_label,
                    "created_at": _iso(s.created_at),
                    "expires_at": _iso(s.expires_at),
                    "revoked_at": _iso(s.revoked_at),
                }
                for s in sessions
            ],
            "subscriptions": [
                {
                    "product_id": s.product_id,
                    "status": s.status,
                    "expires_at": _iso(s.expires_at),
                    "auto_renewing": s.auto_renewing,
                }
                for s in subs
            ],
            "personal_studies": [{"date": _iso(p.date), "payload": p.payload} for p in personal],
            "notes": await NotesService(self.session, self.cipher).export(user.id),
            # o texto do perfil premium entra junto com o serviço de perfil (tarefa 9.1)
            "profile": None
            if profile is None
            else {
                "consent_version": profile.consent_version,
                "consent_at": _iso(profile.consent_at),
            },
        }
