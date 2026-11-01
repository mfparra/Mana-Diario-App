import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.crypto import FieldCipher, get_cipher
from app.core.errors import ApiError
from app.core.ratelimit import NOTES, limit_by_user
from app.db.models import User
from app.db.session import get_session
from app.notes.service import MAX_BODY_CHARS, NoteConflict, NoteFutureDate, NotesService, NoteView

router = APIRouter(prefix="/notes", tags=["notes"], dependencies=[Depends(limit_by_user(NOTES))])


def get_notes_service(
    session: AsyncSession = Depends(get_session), cipher: FieldCipher = Depends(get_cipher)
) -> NotesService:
    return NotesService(session, cipher)


class NoteOut(BaseModel):
    date: dt.date
    body: str | None
    version: int
    updated_at: dt.datetime
    deleted: bool


class NoteList(BaseModel):
    items: list[NoteOut]
    server_time: dt.datetime
    full_sync_required: bool


class NotePut(BaseModel):
    body: str = Field(max_length=MAX_BODY_CHARS)
    base_version: int = Field(ge=0)


class NoteSaved(BaseModel):
    date: dt.date
    version: int
    updated_at: dt.datetime


def _out(v: NoteView) -> NoteOut:
    return NoteOut(date=v.date, body=v.body, version=v.version, updated_at=v.updated_at, deleted=v.deleted)


def _conflict(exc: NoteConflict) -> ApiError:
    cur = exc.current
    details = (
        {
            "body": cur.body,
            "version": cur.version,
            "updated_at": cur.updated_at.isoformat(),
            "deleted": cur.deleted,
        }
        if cur
        else {"body": None, "version": 0, "updated_at": None, "deleted": True}
    )
    return ApiError("note_conflict", "A anotação foi alterada em outro aparelho.", 409, details)


def _future(date: dt.date) -> ApiError:
    return ApiError(
        "future_date", "Ainda não chegou o dia deste devocional.", 422, {"date": date.isoformat()}
    )


@router.get("", response_model=NoteList)
async def list_notes(
    updated_since: Annotated[dt.datetime | None, Query()] = None,
    user: User = Depends(get_current_user),
    svc: NotesService = Depends(get_notes_service),
) -> NoteList:
    if updated_since is not None and updated_since.tzinfo is None:
        updated_since = updated_since.replace(tzinfo=dt.UTC)
    items, server_time, full = await svc.list_since(user.id, updated_since)
    return NoteList(items=[_out(v) for v in items], server_time=server_time, full_sync_required=full)


@router.get("/{date}", response_model=NoteOut)
async def get_note(
    date: dt.date, user: User = Depends(get_current_user), svc: NotesService = Depends(get_notes_service)
) -> NoteOut:
    v = await svc.get(user.id, date)
    if v is None:
        raise ApiError("not_found", "Anotação não encontrada.", 404)
    return _out(v)


@router.put("/{date}", response_model=NoteSaved)
async def put_note(
    date: dt.date,
    body: NotePut,
    user: User = Depends(get_current_user),
    svc: NotesService = Depends(get_notes_service),
) -> NoteSaved:
    try:
        v = await svc.put(user.id, date, body.body, body.base_version)
    except NoteConflict as exc:
        raise _conflict(exc) from None
    except NoteFutureDate:
        raise _future(date) from None
    return NoteSaved(date=v.date, version=v.version, updated_at=v.updated_at)


@router.delete("/{date}", status_code=204)
async def delete_note(
    date: dt.date,
    base_version: Annotated[int, Query(ge=0)],
    user: User = Depends(get_current_user),
    svc: NotesService = Depends(get_notes_service),
) -> Response:
    try:
        await svc.delete(user.id, date, base_version)
    except NoteConflict as exc:
        raise _conflict(exc) from None
    return Response(status_code=204)
