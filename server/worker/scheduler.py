"""Agendador do worker (PLANO 3.8). Um laço simples, uma geração por vez (o llm-server é compartilhado).

A cada tique:
1. Garante estudos de hoje até D+`horizon` (America/Sao_Paulo): datas sem estudo publicado viram jobs.
   - Na janela de lote (padrão 01:00–05:00) enfileira todo o horizonte.
   - Fora dela, só o urgente (hoje e amanhã), para não disputar o llm-server com o BuscaPalavras de dia.
   - Uma data que já falhou `max_failures_per_day` vezes nas últimas 24 h não é tentada de novo
     (o pool de reserva, tarefa 3.9, cobre o dia).
2. Processa os jobs pendentes, por prioridade, um de cada vez.
3. Pool de reserva (3.9): se hoje não tem estudo publicado, publica um da reserva; na janela de lote,
   com o horizonte completo, repõe a reserva até `pool_size`, um estudo por tique.
4. Uma vez por dia: limpeza de tombstones de anotações.
"""

import asyncio
import contextlib
import datetime as dt
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import GenerationJob, Study
from app.domain.calendar import TZ
from app.services import jobs

log = logging.getLogger("worker")

URGENT_PRIORITY = 5


@dataclass
class WorkerConfig:
    horizon_days: int = 7
    batch_start: dt.time = dt.time(1, 0)
    batch_end: dt.time = dt.time(5, 0)
    max_failures_per_day: int = 3
    tick_s: float = 60.0
    pool_size: int = 14


# (sessão, data, force) → status ("published" | "failed" | "skipped")
GenerateFn = Callable[[AsyncSession, dt.date, bool], Awaitable[str]]
MaintenanceFn = Callable[[AsyncSession], Awaitable[None]]
ReserveFn = Callable[[AsyncSession], Awaitable[str]]  # gera um estudo de reserva → status
FallbackFn = Callable[[AsyncSession, dt.date], Awaitable[bool]]  # publica reserva na data → publicou?


def parse_window(spec: str) -> tuple[dt.time, dt.time]:
    """ "01:00-05:00" → (01:00, 05:00)."""
    a, b = (dt.time.fromisoformat(x.strip()) for x in spec.split("-"))
    return a, b


class Worker:
    def __init__(
        self,
        maker: async_sessionmaker[AsyncSession],
        generate: GenerateFn,
        config: WorkerConfig | None = None,
        maintenance: MaintenanceFn | None = None,
        clock: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.UTC),
        reserve: ReserveFn | None = None,
        fallback: FallbackFn | None = None,
        pool_available: Callable[[AsyncSession], Awaitable[int]] | None = None,
    ):
        self.maker = maker
        self.generate = generate
        self.config = config or WorkerConfig()
        self.maintenance = maintenance
        self.clock = clock
        self.reserve = reserve
        self.fallback = fallback
        self.pool_available = pool_available
        self._last_maintenance: dt.date | None = None

    def _local_now(self) -> dt.datetime:
        return self.clock().astimezone(TZ)

    def in_batch_window(self) -> bool:
        t = self._local_now().time()
        a, b = self.config.batch_start, self.config.batch_end
        return a <= t < b if a <= b else (t >= a or t < b)

    async def ensure_horizon(self) -> list[dt.date]:
        """Enfileira as datas do horizonte que ainda não têm estudo publicado. Devolve as enfileiradas."""
        today = self._local_now().date()
        days = self.config.horizon_days if self.in_batch_window() else 1
        wanted = [today + dt.timedelta(days=i) for i in range(days + 1)]
        since = self.clock() - dt.timedelta(hours=24)
        queued = []
        async with self.maker() as s:
            published = set(
                await s.scalars(select(Study.date).where(Study.date.in_(wanted), Study.status == "published"))
            )
            failures = dict(
                (
                    await s.execute(
                        select(GenerationJob.date, func.count())
                        .where(GenerationJob.kind == "daily", GenerationJob.status == "failed",
                               GenerationJob.date.in_(wanted), GenerationJob.updated_at >= since)
                        .group_by(GenerationJob.date)
                    )
                ).all()
            )  # fmt: skip
            for d in wanted:
                if d in published or failures.get(d, 0) >= self.config.max_failures_per_day:
                    continue
                prio = URGENT_PRIORITY if d <= today + dt.timedelta(days=1) else jobs.PRIORITY_NORMAL
                await jobs.enqueue(s, "daily", d, priority=prio)
                queued.append(d)
        return queued

    async def process_one(self) -> bool:
        """Processa um job pendente. False se a fila está vazia."""
        async with self.maker() as s:
            job = await jobs.claim_next(s, self.clock())
            if job is None:
                return False
            job_id, kind, date, prio = job.id, job.kind, job.date, job.priority
        if kind not in ("daily", "reserve") or (kind == "reserve" and self.reserve is None):
            async with self.maker() as s:  # "personal" entra na Fase 9
                await jobs.finish(s, job_id, False, f"tipo de job ainda não suportado: {kind}")
            return True
        force = prio >= jobs.PRIORITY_ADMIN  # regenerate pelo admin refaz mesmo se publicado
        try:
            async with self.maker() as s:
                if kind == "reserve":
                    assert self.reserve is not None
                    status = await self.reserve(s)
                else:
                    status = await self.generate(s, date, force)
            ok, error = status in ("published", "skipped"), None if status != "failed" else "geração falhou"
        except Exception as exc:  # o worker nunca morre por causa de um job
            log.exception("job falhou com exceção", extra={"job_id": job_id, "date": date.isoformat()})
            ok, error = False, type(exc).__name__
        async with self.maker() as s:
            await jobs.finish(s, job_id, ok, error)
        log.info(
            "job concluído",
            extra={"job_id": job_id, "date": date.isoformat(), "event": "ok" if ok else "falha"},
        )
        return True

    async def daily_maintenance(self) -> None:
        today = self._local_now().date()
        if self.maintenance is None or self._last_maintenance == today:
            return
        async with self.maker() as s:
            await self.maintenance(s)
        self._last_maintenance = today

    async def ensure_today(self) -> bool:
        """Hoje sem estudo publicado → publica um da reserva (PLANO 3.9). Devolve se publicou."""
        if self.fallback is None:
            return False
        today = self._local_now().date()
        async with self.maker() as s:
            if await s.scalar(select(Study.date).where(Study.date == today, Study.status == "published")):
                return False
            return await self.fallback(s, today)

    async def ensure_pool(self) -> bool:
        """Na janela de lote, com o horizonte completo, repõe a reserva (um estudo por vez)."""
        if self.reserve is None or self.pool_available is None or not self.in_batch_window():
            return False
        async with self.maker() as s:
            pending_daily = await s.scalar(
                select(func.count())
                .select_from(GenerationJob)
                .where(GenerationJob.kind == "daily", GenerationJob.status.in_(("pending", "running")))
            )
            if pending_daily or await self.pool_available(s) >= self.config.pool_size:
                return False
            await jobs.enqueue(s, "reserve", self._local_now().date(), priority=jobs.PRIORITY_NORMAL - 1)
        return True

    async def tick(self) -> None:
        await self.ensure_today()  # disponibilidade primeiro: hoje não fica sem estudo se houver reserva
        await self.ensure_horizon()
        while await self.process_one():
            pass
        if await self.ensure_pool():
            await self.process_one()
        await self.daily_maintenance()

    async def run(self, stop: asyncio.Event, heartbeat: Callable[[], None] = lambda: None) -> None:
        while not stop.is_set():
            heartbeat()
            try:
                await self.tick()
            except Exception:
                log.exception("erro no tique do worker")
            heartbeat()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=self.config.tick_s)
