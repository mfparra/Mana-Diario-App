"""Pool de reserva e fallback (PLANO 3.9), simulando falha da LLM."""

import datetime as dt

import pytest
from sqlalchemy import func, select, text

from app.db.models import ReserveStudy, Study
from app.domain.study import StudyPayload
from app.services.reserve import available, payload_for, publish_fallback, to_template
from tests.test_generation import _resp, ambiente, biblias  # noqa: F401 — fixtures reaproveitadas
from worker.scheduler import Worker, WorkerConfig

TARDE = dt.datetime(2026, 11, 3, 17, 0, tzinfo=dt.UTC)  # 14:00 em SP, fora da janela
MADRUGADA = dt.datetime(2026, 11, 3, 5, 0, tzinfo=dt.UTC)  # 02:00 em SP
HOJE = dt.date(2026, 11, 3)


@pytest.fixture
async def limpo(ambiente):  # noqa: F811
    maker, service, bible = ambiente
    async with maker() as s:
        await s.execute(text("DELETE FROM reserve_studies"))
        await s.execute(text("DELETE FROM generation_jobs"))
        await s.commit()
    return maker, service, bible


async def _reservar(maker, service, n=2):
    for _ in range(n):
        async with maker() as s:
            svc, _ = service(s, [_resp()])
            svc.clock = lambda: TARDE
            assert (await svc.generate_reserve()).status == "published"


async def test_gera_reserva_sem_data(limpo):
    maker, service, _ = limpo
    async with maker() as s:
        svc, fake = service(s, [_resp()])
        svc.clock = lambda: TARDE
        r = await svc.generate_reserve()
        assert r.status == "published"
        res = (await s.scalars(select(ReserveStudy))).one()
        assert "date" not in res.payload and res.used_on is None
        assert "estudo de reserva" in fake.calls[0][1]["content"]
        assert res.payload["verse"]["text"]  # texto da BLIVRE já resolvido


async def test_reservas_nao_repetem_versiculo(limpo):
    maker, service, _ = limpo
    await _reservar(maker, service, 3)
    async with maker() as s:
        refs = list(await s.scalars(select(ReserveStudy.verse_ref)))
    assert len(set(refs)) == 3


async def test_fallback_quando_a_llm_falha(limpo):
    maker, service, bible = limpo
    await _reservar(maker, service, 2)

    async def gerar_com_llm_fora(session, date, force):
        svc, _ = service(session, ["{}", "{}", "{}"])  # LLM só devolve lixo
        return (await svc.generate(date, force=force)).status

    w = Worker(
        maker, gerar_com_llm_fora, WorkerConfig(horizon_days=0, max_failures_per_day=1), clock=lambda: TARDE,
        fallback=lambda s, d: _publica(s, d), pool_available=available,
    )  # fmt: skip
    await w.tick()  # hoje sem estudo e com reserva → fallback publica antes de tentar a LLM
    async with maker() as s:
        st = await s.get(Study, HOJE)
        assert st.status == "published" and st.is_fallback
        p = StudyPayload.model_validate(st.payload)
        assert p.date == "2026-11-03" and p.day_of_year == 307 and p.special_day is None
        assert p.verse.text == bible.get_text(st.verse_ref)
        usadas = await s.scalar(
            select(func.count()).select_from(ReserveStudy).where(ReserveStudy.used_on == HOJE)
        )
        assert usadas == 1 and await available(s) == 1


async def _publica(session, date):
    return (await publish_fallback(session, date)) is not None


async def test_fallback_nao_substitui_estudo_publicado(limpo):
    maker, service, _ = limpo
    await _reservar(maker, service, 1)
    async with maker() as s:
        svc, _ = service(s, [_resp()])
        await svc.generate(HOJE)
        st = await publish_fallback(s, HOJE)
        assert not st.is_fallback
        assert await available(s) == 1


async def test_sem_reserva_nao_publica(limpo):
    maker, _, _ = limpo
    async with maker() as s:
        assert await publish_fallback(s, HOJE) is None


async def test_worker_repoe_o_pool_na_madrugada(limpo):
    maker, service, _ = limpo

    async def gerar(session, date, force):
        svc, _ = service(session, [_resp()])
        return (await svc.generate(date, force=force)).status

    async def reservar(session):
        svc, _ = service(session, [_resp()])
        return (await svc.generate_reserve()).status

    w = Worker(
        maker, gerar, WorkerConfig(horizon_days=1, pool_size=2), clock=lambda: MADRUGADA,
        reserve=reservar, fallback=_publica, pool_available=available,
    )  # fmt: skip
    for _ in range(4):
        await w.tick()
    async with maker() as s:
        assert await available(s) == 2  # repôs até o tamanho do pool e parou


def test_template_e_payload_por_data():
    from tests.test_studies import EXEMPLO

    tpl = to_template(EXEMPLO)
    assert "date" not in tpl and "generated_at" not in tpl
    p = payload_for(tpl, dt.date(2028, 12, 31), dt.datetime(2028, 1, 1, tzinfo=dt.UTC))
    assert (p["date"], p["day_of_year"], p["days_in_year"]) == ("2028-12-31", 366, 366)
