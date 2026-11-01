"""Fila de geração (`generation_jobs`), processada pelo worker uma requisição por vez."""

import datetime as dt
import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import GenerationJob

PRIORITY_NORMAL = 0
PRIORITY_ADMIN = 10


async def enqueue(
    session: AsyncSession,
    kind: str,
    date: dt.date,
    user_id: uuid.UUID | None = None,
    priority: int = PRIORITY_NORMAL,
) -> GenerationJob:
    """Enfileira (ou reaproveita um pendente igual, subindo a prioridade se preciso)."""
    q = select(GenerationJob).where(
        GenerationJob.kind == kind,
        GenerationJob.date == date,
        GenerationJob.status.in_(("pending", "running")),
    )
    q = q.where(GenerationJob.user_id == user_id) if user_id else q.where(GenerationJob.user_id.is_(None))
    job = await session.scalar(q)
    if job is None:
        job = GenerationJob(kind=kind, date=date, user_id=user_id, priority=priority)
        session.add(job)
    elif job.priority < priority:
        job.priority = priority
    await session.commit()
    return job


async def claim_next(session: AsyncSession, now: dt.datetime | None = None) -> GenerationJob | None:
    """Pega o próximo job pendente (maior prioridade, mais antigo) e marca como `running`."""
    job = await session.scalar(
        select(GenerationJob)
        .where(GenerationJob.status == "pending")
        .order_by(GenerationJob.priority.desc(), GenerationJob.created_at, GenerationJob.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job is None:
        return None
    job.status = "running"
    job.attempts += 1
    job.updated_at = now or dt.datetime.now(dt.UTC)
    await session.commit()
    return job


async def requeue_orphans(session: AsyncSession) -> int:
    """Devolve à fila os jobs `running` deixados por um worker interrompido.

    Só é seguro porque há um único worker (1 requisição por vez à LLM): ao iniciar, nada está rodando.
    Sem isso, `enqueue` acharia o órfão e a data nunca mais seria gerada.
    """
    res = await session.execute(
        update(GenerationJob)
        .where(GenerationJob.status == "running")
        .values(status="pending", updated_at=dt.datetime.now(dt.UTC))
    )
    await session.commit()
    return res.rowcount or 0


async def finish(session: AsyncSession, job_id: int, ok: bool, error: str | None = None) -> None:
    await session.execute(
        update(GenerationJob)
        .where(GenerationJob.id == job_id)
        .values(status="done" if ok else "failed", last_error=(error or None) and error[:500],
                updated_at=dt.datetime.now(dt.UTC))
    )  # fmt: skip
    await session.commit()
