import datetime as dt
from typing import Annotated, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.errors import ApiError
from app.db.models import Study
from app.db.session import get_session
from app.services.studies import MAX_RANGE_DAYS, FutureDate, InvalidRange, StudyService

router = APIRouter(prefix="/studies", tags=["studies"], dependencies=[Depends(get_current_user)])

CACHE_CONTROL = "private, max-age=300"


def get_study_service(session: AsyncSession = Depends(get_session)) -> StudyService:
    return StudyService(session)


class StudySummary(BaseModel):
    date: dt.date
    title: str
    verse_ref: str
    keywords: list[str]


class StudyList(BaseModel):
    items: list[StudySummary]


def _not_available(date: dt.date) -> ApiError:
    return ApiError(
        "study_not_available",
        "O estudo deste dia ainda não está disponível.",
        404,
        {"date": date.isoformat()},
    )


def _future(date: dt.date, max_date: dt.date) -> ApiError:
    return ApiError(
        "future_date",
        "Ainda não chegou o dia deste estudo.",
        422,
        {"date": date.isoformat(), "max_date": max_date.isoformat()},
    )


def _etag_matches(request: Request, etag: str) -> bool:
    header = request.headers.get("if-none-match", "")
    candidates = {t.strip().removeprefix("W/").strip('"') for t in header.split(",") if t.strip()}
    return etag in candidates or "*" in candidates


def _study_response(request: Request, study: Study) -> Response:
    assert study.etag is not None
    headers = {"ETag": f'"{study.etag}"', "Cache-Control": CACHE_CONTROL}
    if _etag_matches(request, study.etag):
        return Response(status_code=304, headers=headers)
    return JSONResponse(study.payload, headers=headers)


async def _serve(request: Request, svc: StudyService, date: dt.date) -> Response:
    try:
        study = await svc.get_published(date)
    except FutureDate:
        raise _future(date, svc.max_date()) from None
    if study is None:
        raise _not_available(date)
    return _study_response(request, study)


@router.get("/today", responses={200: {"description": "Objeto Study (ver docs/API.md)"}, 304: {}})
async def today(
    request: Request,
    tz: Annotated[str | None, Query(max_length=64, description="Fuso IANA do aparelho")] = None,
    svc: StudyService = Depends(get_study_service),
) -> Response:
    if tz is not None:
        try:
            ZoneInfo(tz)
        except (ZoneInfoNotFoundError, ValueError):
            fields = [{"loc": ["query", "tz"], "type": "timezone"}]
            raise ApiError("validation_error", "Fuso horário inválido.", 422, {"fields": fields}) from None
    return await _serve(request, svc, svc.today_for(tz))


@router.get("", response_model=StudyList)
async def list_studies(
    from_: Annotated[dt.date, Query(alias="from")],
    to: dt.date,
    svc: StudyService = Depends(get_study_service),
) -> StudyList:
    try:
        rows = await svc.list_published(from_, to)
    except InvalidRange:
        raise ApiError(
            "validation_error",
            f"Intervalo inválido: use de 1 a {MAX_RANGE_DAYS} dias, com from ≤ to.",
            422,
            {"fields": [{"loc": ["query", "from"], "type": "range"}]},
        ) from None
    return StudyList(items=[_summary(s) for s in rows])


def _summary(s: Study) -> StudySummary:
    p: dict[str, Any] = s.payload or {}
    return StudySummary(
        date=s.date, title=p.get("title", ""), verse_ref=s.verse_ref, keywords=p.get("keywords", [])
    )


@router.get("/{date}", responses={200: {"description": "Objeto Study (ver docs/API.md)"}, 304: {}})
async def by_date(
    request: Request, date: dt.date, svc: StudyService = Depends(get_study_service)
) -> Response:
    return await _serve(request, svc, date)
