"""Login com Google, emissão de tokens próprios (DECISOES A2/A3)."""

import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import create_access_token, hash_token, new_refresh_token
from app.db.models import RefreshToken, User
from app.services.google_id import GoogleIdTokenVerifier

ACCESS_TTL_S = 30 * 60
REFRESH_TTL_S = 60 * 24 * 3600
# Repetição do mesmo refresh logo após a rotação (ex.: app reenviou por falha de rede) não é tratada
# como roubo: só recebe 401, sem revogar as outras sessões.
REUSE_GRACE_S = 15


class InvalidRefreshToken(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason  # unknown | expired | revoked | reused | reused_grace | user_gone


@dataclass
class TokenPair:
    access_token: str
    access_expires_in: int
    refresh_token: str
    refresh_expires_in: int


@dataclass
class LoginResult:
    tokens: TokenPair
    user: User
    created: bool


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings, verifier: GoogleIdTokenVerifier):
        self.session = session
        self.settings = settings
        self.verifier = verifier

    async def _issue(
        self,
        user: User,
        device_label: str | None,
        family_id: uuid.UUID | None = None,
        now: dt.datetime | None = None,
    ) -> tuple[TokenPair, RefreshToken]:
        now = now or dt.datetime.now(dt.UTC)
        refresh = new_refresh_token()
        row = RefreshToken(
            id=uuid.uuid4(),
            user_id=user.id,
            family_id=family_id or uuid.uuid4(),
            token_hash=hash_token(refresh),
            device_label=(device_label or None) and device_label[:100],
            expires_at=now + dt.timedelta(seconds=REFRESH_TTL_S),
        )
        self.session.add(row)
        access = create_access_token(user.id, self.settings.jwt_secret, ACCESS_TTL_S, now)
        return TokenPair(access, ACCESS_TTL_S, refresh, REFRESH_TTL_S), row

    async def login_google(self, id_token: str, device_label: str | None) -> LoginResult:
        identity = await self.verifier.verify(id_token)  # InvalidGoogleToken → 401 no router
        user = await self.session.scalar(select(User).where(User.google_sub == identity.sub))
        created = user is None
        if user is None:
            user = User(id=uuid.uuid4(), google_sub=identity.sub, email=identity.email)
            self.session.add(user)
        user.email = identity.email
        user.name = identity.name
        user.photo_url = identity.photo_url
        user.updated_at = dt.datetime.now(dt.UTC)
        await self.session.flush()
        tokens, _ = await self._issue(user, device_label)
        await self.session.commit()
        return LoginResult(tokens, user, created)

    async def refresh(self, refresh_token: str, now: dt.datetime | None = None) -> TokenPair:
        now = now or dt.datetime.now(dt.UTC)
        row = await self.session.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == hash_token(refresh_token)).with_for_update()
        )
        if row is None:
            raise InvalidRefreshToken("unknown")
        if row.revoked_at is not None:
            if row.replaced_by_id is None:
                raise InvalidRefreshToken("revoked")  # encerrado por logout: só 401
            if (now - row.revoked_at).total_seconds() <= REUSE_GRACE_S:
                raise InvalidRefreshToken("reused_grace")
            # reuso de token já ROTACIONADO = possível roubo → derruba todas as sessões do usuário
            await self.revoke_all(row.user_id, now)
            await self.session.commit()
            raise InvalidRefreshToken("reused")
        if row.expires_at <= now:
            raise InvalidRefreshToken("expired")
        user = await self.session.get(User, row.user_id)
        if user is None or user.deleted_at is not None:
            raise InvalidRefreshToken("user_gone")
        tokens, new_row = await self._issue(user, row.device_label, family_id=row.family_id, now=now)
        await self.session.flush()
        row.revoked_at = now
        row.replaced_by_id = new_row.id
        await self.session.commit()
        return tokens

    async def logout(self, refresh_token: str, now: dt.datetime | None = None) -> None:
        """Encerra a sessão deste aparelho (a família inteira do token). Idempotente."""
        now = now or dt.datetime.now(dt.UTC)
        row = await self.session.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == hash_token(refresh_token))
        )
        if row is not None:
            await self.session.execute(
                update(RefreshToken)
                .where(RefreshToken.family_id == row.family_id, RefreshToken.revoked_at.is_(None))
                .values(revoked_at=now)
            )
            await self.session.commit()

    async def revoke_all(self, user_id: uuid.UUID, now: dt.datetime | None = None) -> None:
        await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now or dt.datetime.now(dt.UTC))
        )
