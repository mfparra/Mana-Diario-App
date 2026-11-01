"""Carga dos dados de conteúdo versionados em `server/data/` para o banco (idempotente).

`python -m app.cli carregar-dados` — rodar após editar os arquivos (o passo `migrate` do compose também roda).
Entradas removidas do arquivo ficam `active = false` (o histórico de estudos continua apontando para elas).
"""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import VersePlan
from app.domain.verse_plan import PlanEntry


@dataclass
class SyncReport:
    inserted: int = 0
    updated: int = 0
    deactivated: int = 0


async def sync_verse_plan(session: AsyncSession, entries: Sequence[PlanEntry]) -> SyncReport:
    report = SyncReport()
    existing = {(r.verse_ref, r.special_day): r for r in (await session.scalars(select(VersePlan))).all()}
    wanted: set[tuple[str, str | None]] = set()
    for pos, e in enumerate(entries):
        key = (e.ref, e.special_day)
        wanted.add(key)
        row = existing.get(key)
        if row is None:
            session.add(VersePlan(verse_ref=e.ref, theme=e.theme, special_day=e.special_day, position=pos))
            report.inserted += 1
        elif (row.theme, row.position, row.active) != (e.theme, pos, True):
            row.theme, row.position, row.active = e.theme, pos, True
            report.updated += 1
    for key, row in existing.items():
        if key not in wanted and row.active:
            row.active = False
            report.deactivated += 1
    await session.commit()
    return report


async def load_active_plan(session: AsyncSession) -> list[PlanEntry]:
    rows = await session.scalars(select(VersePlan).where(VersePlan.active).order_by(VersePlan.position))
    return [PlanEntry(r.verse_ref, r.theme or "", r.special_day) for r in rows]
