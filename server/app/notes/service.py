"""Anotações por devocional (DECISOES N1–N7): uma por (usuário, data), cifradas em repouso,
versão otimista e tombstones para propagar exclusões entre aparelhos.

O texto **nunca** é logado nem enviado à LLM.
"""

import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import FieldCipher
from app.db.models import Note
from app.domain.calendar import today

MAX_BODY_CHARS = 10_000
TOMBSTONE_RETENTION_DAYS = 30
# server_time devolvido fica um pouco no passado: escritas concorrentes não escapam do próximo pull
# (no máximo vêm repetidas, o que o app trata como idempotente).
CLOCK_SKEW_S = 5


@dataclass
class NoteView:
    date: dt.date
    body: str | None  # None = excluída (tombstone)
    version: int
    updated_at: dt.datetime

    @property
    def deleted(self) -> bool:
        return self.body is None


class NoteConflict(Exception):
    def __init__(self, current: NoteView | None):
        super().__init__("note_conflict")
        self.current = current


class NoteFutureDate(Exception):
    pass


def _aad(user_id: uuid.UUID, date: dt.date) -> str:
    return f"note:{user_id}:{date.isoformat()}"


class NotesService:
    def __init__(self, session: AsyncSession, cipher: FieldCipher):
        self.session = session
        self.cipher = cipher

    def _view(self, n: Note) -> NoteView:
        body = (
            None
            if n.encrypted_body is None
            else self.cipher.decrypt(n.encrypted_body, _aad(n.user_id, n.date))
        )
        return NoteView(n.date, body, n.version, n.updated_at)

    async def list_since(
        self, user_id: uuid.UUID, since: dt.datetime | None, now: dt.datetime | None = None
    ) -> tuple[list[NoteView], dt.datetime, bool]:
        """(itens alterados depois de `since`, server_time, full_sync_required)."""
        now = now or dt.datetime.now(dt.UTC)
        server_time = now - dt.timedelta(seconds=CLOCK_SKEW_S)
        # tombstones antigos já foram limpos: quem está há muito tempo sem sincronizar refaz tudo
        full = since is not None and since < now - dt.timedelta(days=TOMBSTONE_RETENTION_DAYS)
        q = select(Note).where(Note.user_id == user_id)
        if since is not None and not full:
            q = q.where(Note.updated_at > since)
        if full or since is None:
            q = q.where(Note.deleted_at.is_(None))
        rows = await self.session.scalars(q.order_by(Note.updated_at))
        return [self._view(n) for n in rows], server_time, full

    async def get(self, user_id: uuid.UUID, date: dt.date) -> NoteView | None:
        n = await self.session.get(Note, (user_id, date))
        return None if n is None or n.deleted_at is not None else self._view(n)

    def _check_date(self, date: dt.date, now: dt.datetime) -> None:
        if date > today(now) + dt.timedelta(days=1):
            raise NoteFutureDate(date)

    async def put(
        self, user_id: uuid.UUID, date: dt.date, body: str, base_version: int, now: dt.datetime | None = None
    ) -> NoteView:
        now = now or dt.datetime.now(dt.UTC)
        self._check_date(date, now)
        enc = self.cipher.encrypt(body, _aad(user_id, date))
        row = await self.session.scalar(
            select(Note).where(Note.user_id == user_id, Note.date == date).with_for_update()
        )
        if row is None:
            if base_version != 0:
                raise NoteConflict(None)
            row = Note(user_id=user_id, date=date, encrypted_body=enc, version=1, updated_at=now)
            self.session.add(row)
            try:
                await self.session.commit()
            except IntegrityError:  # outro aparelho criou ao mesmo tempo
                await self.session.rollback()
                raise NoteConflict(await self._current(user_id, date)) from None
            return self._view(row)
        if row.version != base_version:
            raise NoteConflict(self._view(row))
        row.encrypted_body = enc
        row.deleted_at = None
        row.version += 1
        row.updated_at = now
        await self.session.commit()
        return self._view(row)

    async def delete(
        self, user_id: uuid.UUID, date: dt.date, base_version: int, now: dt.datetime | None = None
    ) -> None:
        now = now or dt.datetime.now(dt.UTC)
        row = await self.session.scalar(
            select(Note).where(Note.user_id == user_id, Note.date == date).with_for_update()
        )
        if row is None or row.deleted_at is not None:
            return  # idempotente
        if row.version != base_version:
            raise NoteConflict(self._view(row))
        row.encrypted_body = None
        row.deleted_at = now
        row.version += 1
        row.updated_at = now
        await self.session.commit()

    async def _current(self, user_id: uuid.UUID, date: dt.date) -> NoteView | None:
        n = await self.session.get(Note, (user_id, date), populate_existing=True)
        return None if n is None else self._view(n)

    async def export(self, user_id: uuid.UUID) -> list[dict]:
        rows = await self.session.scalars(
            select(Note).where(Note.user_id == user_id, Note.deleted_at.is_(None)).order_by(Note.date)
        )
        return [
            {
                "date": v.date.isoformat(),
                "body": v.body,
                "version": v.version,
                "updated_at": v.updated_at.isoformat(),
            }
            for v in (self._view(n) for n in rows)
        ]

    async def purge_tombstones(self, now: dt.datetime | None = None) -> int:
        return await purge_tombstones(self.session, now)


async def purge_tombstones(session: AsyncSession, now: dt.datetime | None = None) -> int:
    """Apaga tombstones com mais de 30 dias (rodado pelo worker; não precisa da chave)."""
    now = now or dt.datetime.now(dt.UTC)
    limit = now - dt.timedelta(days=TOMBSTONE_RETENTION_DAYS)
    res = await session.execute(delete(Note).where(Note.deleted_at.is_not(None), Note.deleted_at < limit))
    await session.commit()
    return res.rowcount or 0
