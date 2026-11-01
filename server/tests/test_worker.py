"""Worker (PLANO 3.8): horizonte, janela de lote, fila por prioridade, limite de falhas, manutenção."""

import asyncio
import datetime as dt

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.services import jobs
from worker.scheduler import Worker, WorkerConfig, parse_window

# 01/11/2026 02:00 em São Paulo (05:00 UTC) — dentro da janela 01:00–05:00
MADRUGADA = dt.datetime(2026, 11, 1, 5, 0, tzinfo=dt.UTC)
# 01/11/2026 14:00 em São Paulo
TARDE = dt.datetime(2026, 11, 1, 17, 0, tzinfo=dt.UTC)
HOJE = dt.date(2026, 11, 1)


@pytest.fixture
async def maker(migrated_db_url):
    engine = create_async_engine(migrated_db_url)
    mk = async_sessionmaker(engine, expire_on_commit=False)
    async with mk() as s:
        await s.execute(text("DELETE FROM generation_jobs"))
        await s.execute(text("DELETE FROM studies"))
        await s.commit()
    yield mk
    await engine.dispose()


class FakeGen:
    """Simula o GenerationService: publica (ou falha) gravando em `studies`."""

    def __init__(self, falhar: set[dt.date] = frozenset()):
        self.chamadas: list[tuple[dt.date, bool]] = []
        self.falhar = falhar
        self.em_andamento = 0
        self.max_simultaneas = 0

    async def __call__(self, session, date, force):
        self.em_andamento += 1
        self.max_simultaneas = max(self.max_simultaneas, self.em_andamento)
        try:
            self.chamadas.append((date, force))
            await asyncio.sleep(0)
            status = "failed" if date in self.falhar else "published"
            await session.execute(
                text(
                    "INSERT INTO studies (date, status, payload, verse_ref) VALUES (:d, CAST(:s AS varchar), "
                    "CASE WHEN CAST(:s AS varchar) = 'published' THEN CAST('{}' AS jsonb) END, 'JHN 3:16') "
                    "ON CONFLICT (date) DO UPDATE SET status = EXCLUDED.status, payload = EXCLUDED.payload"
                ),
                {"d": date, "s": status},
            )
            await session.commit()
            return status
        finally:
            self.em_andamento -= 1


def test_janela():
    assert parse_window("01:00-05:00") == (dt.time(1), dt.time(5))
    assert parse_window("23:30-04:00") == (dt.time(23, 30), dt.time(4))


async def test_madrugada_gera_o_horizonte_inteiro_um_por_vez(maker):
    gen = FakeGen()
    w = Worker(maker, gen, WorkerConfig(horizon_days=7), clock=lambda: MADRUGADA)
    await w.tick()
    datas = [d for d, _ in gen.chamadas]
    assert datas[:2] == [HOJE, HOJE + dt.timedelta(days=1)]  # urgentes primeiro
    assert sorted(datas) == [HOJE + dt.timedelta(days=i) for i in range(8)]  # hoje..D+7
    assert gen.max_simultaneas == 1
    gen.chamadas.clear()
    await w.tick()  # tudo publicado → nada a fazer
    assert gen.chamadas == []


async def test_de_dia_so_gera_o_urgente(maker):
    gen = FakeGen()
    await Worker(maker, gen, WorkerConfig(horizon_days=7), clock=lambda: TARDE).tick()
    assert sorted(d for d, _ in gen.chamadas) == [HOJE, HOJE + dt.timedelta(days=1)]


async def test_limite_de_falhas_por_dia(maker):
    gen = FakeGen(falhar={HOJE})
    w = Worker(maker, gen, WorkerConfig(horizon_days=0, max_failures_per_day=3), clock=lambda: TARDE)
    for _ in range(5):
        await w.tick()
    assert [d for d, _ in gen.chamadas].count(HOJE) == 3  # depois da 3ª falha, para (pool de reserva cobre)


async def test_job_do_admin_tem_prioridade_e_usa_force(maker):
    gen = FakeGen()
    async with maker() as s:
        await jobs.enqueue(s, "daily", dt.date(2026, 10, 20), priority=jobs.PRIORITY_ADMIN)
    await Worker(maker, gen, WorkerConfig(horizon_days=0), clock=lambda: TARDE).tick()
    assert gen.chamadas[0] == (dt.date(2026, 10, 20), True)
    assert all(not force for d, force in gen.chamadas[1:])


async def test_excecao_no_job_nao_derruba_o_worker(maker):
    async def explode(session, date, force):
        raise RuntimeError("falha inesperada")

    w = Worker(maker, explode, WorkerConfig(horizon_days=0), clock=lambda: TARDE)
    await w.tick()
    async with maker() as s:
        st = (await s.execute(text("SELECT status, last_error FROM generation_jobs"))).all()
    assert st and all(r[0] == "failed" and r[1] == "RuntimeError" for r in st)


async def test_manutencao_uma_vez_por_dia(maker):
    chamadas = []

    async def manut(session):
        chamadas.append(1)

    agora = [TARDE]
    w = Worker(maker, FakeGen(), WorkerConfig(horizon_days=0), maintenance=manut, clock=lambda: agora[0])
    await w.tick()
    await w.tick()
    agora[0] = TARDE + dt.timedelta(days=1)
    await w.tick()
    assert len(chamadas) == 2


async def test_job_orfao_volta_para_a_fila_ao_iniciar(maker):
    async with maker() as s:
        await jobs.enqueue(s, "daily", HOJE)
        assert (await jobs.claim_next(s)).status == "running"  # worker anterior morreu aqui
    gen = FakeGen()
    stop = asyncio.Event()
    w = Worker(maker, gen, WorkerConfig(horizon_days=0, tick_s=0.01), clock=lambda: TARDE)
    task = asyncio.create_task(w.run(stop))
    await asyncio.sleep(0.05)
    stop.set()
    await asyncio.wait_for(task, 2)
    assert HOJE in [d for d, _ in gen.chamadas]
    async with maker() as s:
        st = (await s.execute(text("SELECT status FROM generation_jobs"))).scalars().all()
    assert "running" not in st


async def test_run_para_no_sinal(maker):
    stop = asyncio.Event()
    batidas = []
    w = Worker(maker, FakeGen(), WorkerConfig(horizon_days=0, tick_s=0.01), clock=lambda: TARDE)
    task = asyncio.create_task(w.run(stop, heartbeat=lambda: batidas.append(1)))
    await asyncio.sleep(0.05)
    stop.set()
    await asyncio.wait_for(task, 2)
    assert batidas
