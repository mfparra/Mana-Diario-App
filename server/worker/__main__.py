"""Processo do worker: `python -m worker` (contêiner `worker`).

Gera os estudos do horizonte (hoje..D+7) e processa a fila; ver `worker/scheduler.py`.
"""

import asyncio
import contextlib
import logging
import signal
import time

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.bible.crossrefs import CrossReferenceRepository
from app.bible.repository import BibleRepository
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.llm import get_llm_client
from app.notes.service import purge_tombstones
from app.services.generation import GenerationService
from app.services.reserve import available, publish_fallback
from worker.healthcheck import HEARTBEAT, INTERVAL_S
from worker.scheduler import Worker, WorkerConfig, parse_window

log = logging.getLogger("worker")


def beat() -> None:
    HEARTBEAT.write_text(str(time.time()))


async def heartbeat_loop(stop: asyncio.Event) -> None:
    # tarefa própria: uma geração lenta (minutos) não deixa o healthcheck vencer
    while not stop.is_set():
        beat()
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=INTERVAL_S)


async def main() -> None:
    setup_logging()
    settings = get_settings()
    if not settings.database_url:
        raise SystemExit("DATABASE_URL não configurada")
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    bible = BibleRepository(settings.blivre_sqlite_path)
    xr = CrossReferenceRepository(settings.crossrefs_sqlite_path, bible)
    llm = get_llm_client(settings)

    async def generate(session, date, force):
        return (await GenerationService(session, bible, xr, llm).generate(date, force=force)).status

    async def reserve(session):
        return (await GenerationService(session, bible, xr, llm).generate_reserve()).status

    async def fallback(session, date):
        return (await publish_fallback(session, date)) is not None

    async def maintenance(session):
        n = await purge_tombstones(session)
        log.info("manutenção diária", extra={"event": "purge_tombstones", "count": n})

    start, end = parse_window(settings.worker_batch_window)
    cfg = WorkerConfig(horizon_days=settings.worker_horizon_days, batch_start=start, batch_end=end,
                       tick_s=settings.worker_tick_s)  # fmt: skip
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    log.info("worker iniciado", extra={"provider": llm.provider, "model": llm.model})
    beat()
    try:
        worker = Worker(
            maker, generate, cfg, maintenance, reserve=reserve, fallback=fallback, pool_available=available
        )
        await asyncio.gather(heartbeat_loop(stop), worker.run(stop))
    finally:
        await engine.dispose()
        log.info("worker encerrado")


if __name__ == "__main__":
    asyncio.run(main())
