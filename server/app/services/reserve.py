"""Pool de reserva (PLANO 3.9): estudos genéricos já validados que cobrem um dia sem estudo publicado.

- Gerados pelo worker na madrugada, depois do horizonte, até `POOL_SIZE` disponíveis.
- Usam versículos de dias comuns que não saíram nos últimos 365 dias, que não estão em outra reserva e
  que estão longe de voltar no rodízio (metade do plano à frente do último usado).
- Fallback: se hoje (São Paulo) não tem estudo publicado, publica a reserva mais antiga com a data de hoje.
"""

import calendar
import datetime as dt
import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ReserveStudy, Study
from app.domain.study import StudyPayload
from app.services.studies import compute_etag

log = logging.getLogger("app.reserve")

POOL_SIZE = 14
DATE_FIELDS = ("date", "day_of_year", "days_in_year", "special_day", "generated_at")


def to_template(payload: dict) -> dict:
    return {k: v for k, v in payload.items() if k not in DATE_FIELDS}


def payload_for(template: dict, date: dt.date, generated_at: dt.datetime) -> dict:
    full = {
        **template,
        "date": date.isoformat(),
        "day_of_year": date.timetuple().tm_yday,
        "days_in_year": 366 if calendar.isleap(date.year) else 365,
        "special_day": None,
        "generated_at": generated_at.isoformat().replace("+00:00", "Z"),
    }
    return StudyPayload.model_validate(full).model_dump(mode="json")


async def available(session: AsyncSession) -> int:
    return await session.scalar(
        select(func.count()).select_from(ReserveStudy).where(ReserveStudy.used_on.is_(None))
    )


async def publish_fallback(session: AsyncSession, date: dt.date) -> Study | None:
    """Publica a reserva mais antiga em `date` (se houver). Idempotente: não mexe em estudo já publicado."""
    study = await session.get(Study, date, with_for_update=True)
    if study is not None and study.status == "published":
        return study
    reserve = await session.scalar(
        select(ReserveStudy)
        .where(ReserveStudy.used_on.is_(None))
        .order_by(ReserveStudy.created_at, ReserveStudy.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if reserve is None:
        log.error("sem estudo publicado e sem reserva disponível", extra={"date": date.isoformat()})
        return None
    payload = payload_for(reserve.payload, date, reserve.created_at)
    if study is None:
        study = Study(date=date, verse_ref=reserve.verse_ref)
        session.add(study)
    now = dt.datetime.now(dt.UTC)
    study.verse_ref = reserve.verse_ref
    study.special_day = None
    study.quote_id = reserve.quote_id
    study.payload = payload
    study.etag = compute_etag(payload)
    study.status = "published"
    study.is_fallback = True
    study.provider, study.model, study.prompt_version = (
        reserve.provider,
        reserve.model,
        reserve.prompt_version,
    )
    study.generated_at = reserve.created_at
    study.published_at = now
    reserve.used_on = date
    await session.commit()
    log.warning("estudo de reserva publicado", extra={"date": date.isoformat(), "event": "fallback"})
    return study
