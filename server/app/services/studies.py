"""Leitura dos estudos publicados (a geração fica no GenerationService, Fase 3).

"Hoje" = data civil em America/Sao_Paulo (DECISOES S6). Aceita até D+1 para quem está em fusos a leste.
"""

import datetime as dt
import hashlib
import json
from collections.abc import Callable
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import Study
from app.domain.calendar import today

MAX_RANGE_DAYS = 62
FUTURE_TOLERANCE_DAYS = 1

Clock = Callable[[], dt.datetime]


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def compute_etag(payload: dict[str, Any]) -> str:
    """Hash estável do payload (chaves ordenadas) — o mesmo estudo sempre gera o mesmo ETag."""
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:32]


class FutureDate(Exception):
    pass


class InvalidRange(Exception):
    pass


class StudyService:
    def __init__(self, session: AsyncSession, clock: Clock = utc_now):
        self.session = session
        self.clock = clock

    def server_today(self) -> dt.date:
        return today(self.clock())

    def max_date(self) -> dt.date:
        return self.server_today() + dt.timedelta(days=FUTURE_TOLERANCE_DAYS)

    def today_for(self, tz: str | None) -> dt.date:
        """Data de hoje no fuso do aparelho, limitada a D+1 do servidor."""
        local = self.clock().astimezone(ZoneInfo(tz)).date() if tz else self.server_today()
        return min(local, self.max_date())

    async def get_published(self, date: dt.date) -> Study | None:
        if date > self.max_date():
            raise FutureDate(date)
        study = await self.session.get(Study, date)
        if study is None or study.status != "published" or study.payload is None:
            return None
        if study.etag is None:
            study.etag = compute_etag(study.payload)
        return study

    async def list_published(self, start: dt.date, end: dt.date) -> list[Study]:
        if end < start or (end - start).days + 1 > MAX_RANGE_DAYS:
            raise InvalidRange(f"intervalo de 1 a {MAX_RANGE_DAYS} dias")
        end = min(end, self.max_date())
        rows = await self.session.scalars(
            select(Study)
            .where(Study.date.between(start, end), Study.status == "published")
            .order_by(Study.date.desc())
        )
        return list(rows)


async def is_published(engine: AsyncEngine | None, date: dt.date) -> bool:
    """Usado pelo /health. Nunca levanta exceção."""
    if engine is None:
        return False
    try:
        async with engine.connect() as conn:
            row = await conn.execute(
                text("SELECT 1 FROM studies WHERE date = :d AND status = 'published'"), {"d": date}
            )
            return row.first() is not None
    except Exception:
        return False
