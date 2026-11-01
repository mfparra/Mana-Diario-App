"""Endpoints de administração (docs/API.md "Infra / Admin"), protegidos por `X-Admin-Token`.

Não são usados pelo app. Em produção, o proxy pode ainda restringir `/v1/admin/*` por IP.
"""

import datetime as dt
import hmac
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.db.models import GenerationJob, Study
from app.db.session import get_session
from app.services.jobs import PRIORITY_ADMIN, enqueue


def require_admin(
    x_admin_token: Annotated[str | None, Header()] = None, settings: Settings = Depends(get_settings)
) -> None:
    if not settings.admin_token:
        raise ApiError("unavailable", "Administração desativada (ADMIN_TOKEN não configurado).", 503)
    if not x_admin_token or not hmac.compare_digest(x_admin_token.encode(), settings.admin_token.encode()):
        raise ApiError("forbidden", "Acesso negado.", 403)


router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


class AdminStudy(BaseModel):
    date: dt.date
    status: str
    verse_ref: str
    title: str | None
    provider: str | None
    model: str | None
    prompt_version: str | None
    generated_at: dt.datetime | None
    published_at: dt.datetime | None
    last_error: str | None


class AdminStudyList(BaseModel):
    items: list[AdminStudy]


class JobOut(BaseModel):
    job_id: int
    status: str


async def _last_errors(session: AsyncSession, dates: list[dt.date]) -> dict[dt.date, str]:
    rows = await session.execute(
        select(GenerationJob.date, GenerationJob.last_error)
        .where(
            GenerationJob.kind == "daily",
            GenerationJob.date.in_(dates),
            GenerationJob.last_error.is_not(None),
        )
        .order_by(GenerationJob.updated_at)
    )
    return {d: e for d, e in rows}


@router.get("/studies", response_model=AdminStudyList)
async def list_studies(
    status: Annotated[Literal["draft", "published", "failed"] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 60,
    session: AsyncSession = Depends(get_session),
) -> AdminStudyList:
    q = select(Study).order_by(Study.date.desc()).limit(limit)
    if status:
        q = q.where(Study.status == status)
    rows = (await session.scalars(q)).all()
    errors = await _last_errors(session, [s.date for s in rows])
    return AdminStudyList(
        items=[
            AdminStudy(
                date=s.date, status=s.status, verse_ref=s.verse_ref, title=(s.payload or {}).get("title"),
                provider=s.provider, model=s.model, prompt_version=s.prompt_version,
                generated_at=s.generated_at, published_at=s.published_at, last_error=errors.get(s.date),
            )
            for s in rows
        ]
    )  # fmt: skip


@router.post("/studies/{date}/regenerate", status_code=202, response_model=JobOut)
async def regenerate(date: dt.date, session: AsyncSession = Depends(get_session)) -> JobOut:
    """Enfileira a geração (com force) para o worker; com LLM local leva minutos."""
    job = await enqueue(session, "daily", date, priority=PRIORITY_ADMIN)
    return JobOut(job_id=job.id, status=job.status)


async def _get(session: AsyncSession, date: dt.date) -> Study:
    study = await session.get(Study, date)
    if study is None:
        raise ApiError("not_found", "Estudo não encontrado.", 404)
    return study


@router.post("/studies/{date}/publish", response_model=AdminStudy)
async def publish(date: dt.date, session: AsyncSession = Depends(get_session)) -> AdminStudy:
    study = await _get(session, date)
    if study.payload is None:
        raise ApiError("conflict", "Estudo sem conteúdo gerado; use regenerate.", 409)
    study.status = "published"
    study.published_at = dt.datetime.now(dt.UTC)
    await session.commit()
    return await _one(session, study)


@router.post("/studies/{date}/unpublish", response_model=AdminStudy)
async def unpublish(date: dt.date, session: AsyncSession = Depends(get_session)) -> AdminStudy:
    """Tira do ar (vira rascunho, conteúdo preservado). O app passa a receber 404 nessa data."""
    study = await _get(session, date)
    study.status = "draft"
    await session.commit()
    return await _one(session, study)


async def _one(session: AsyncSession, s: Study) -> AdminStudy:
    err = (await _last_errors(session, [s.date])).get(s.date)
    return AdminStudy(
        date=s.date, status=s.status, verse_ref=s.verse_ref, title=(s.payload or {}).get("title"),
        provider=s.provider, model=s.model, prompt_version=s.prompt_version,
        generated_at=s.generated_at, published_at=s.published_at, last_error=err,
    )  # fmt: skip
