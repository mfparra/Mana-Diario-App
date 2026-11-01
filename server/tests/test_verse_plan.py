import datetime as dt
from collections import Counter
from pathlib import Path

import pytest
from blivre.importar import build_database

from app.bible.repository import BibleRepository
from app.domain.calendar import SPECIAL_DAYS, special_day_for
from app.domain.verse_plan import NO_REPEAT_DAYS, PlanEntry, PlanError, choose_verse, load_plan, plan_issues

FONTE = Path(__file__).resolve().parents[2] / "tools/biblia/fonte/porbr2018_usfm.zip"


@pytest.fixture(scope="module")
def plano():
    return load_plan()


@pytest.fixture(scope="module")
def bible(tmp_path_factory):
    db = tmp_path_factory.mktemp("b") / "blivre.sqlite"
    build_database(FONTE, db)
    repo = BibleRepository(db)
    yield repo
    repo.close()


def test_acervo_dura_mais_de_um_ano(plano):
    comuns = [e for e in plano if e.special_day is None]
    assert len(comuns) >= 366
    assert plan_issues(plano) == []


def test_todas_as_referencias_existem_na_blivre(plano, bible):
    assert [e.ref for e in plano if not bible.exists(e.ref)] == []


def test_toda_data_especial_tem_versiculos(plano):
    chaves = {e.special_day for e in plano if e.special_day}
    assert chaves == {d.key for d in SPECIAL_DAYS}


def test_temas_intercalados(plano):
    comuns = [e for e in plano if e.special_day is None]
    temas = [e.theme for e in comuns[:20]]
    assert len(set(temas)) == 20  # os primeiros 20 dias são de 20 temas diferentes


def _simular(plano, inicio: dt.date, dias: int):
    hist: list[tuple[dt.date, str]] = []
    escolhas = []
    for i in range(dias):
        d = inicio + dt.timedelta(days=i)
        c = choose_verse(d, plano, hist)
        hist.append((d, c.ref))
        escolhas.append((d, c))
    return escolhas


def test_simulacao_de_dois_anos_sem_repeticao_indevida(plano):
    escolhas = _simular(plano, dt.date(2026, 11, 1), 2 * 366)
    ultimo: dict[str, dt.date] = {}
    for d, c in escolhas:
        if c.special_day is None and c.ref in ultimo:
            assert (d - ultimo[c.ref]).days > NO_REPEAT_DAYS, (
                f"{c.ref} repetiu em {d} (antes: {ultimo[c.ref]})"
            )
        ultimo[c.ref] = d
        # data especial sempre usa o conjunto daquela data
        sd = special_day_for(d)
        assert c.special_day == (sd.key if sd else None)
    usados = Counter(c.ref for _, c in escolhas if c.special_day is None)
    assert max(usados.values()) <= 2


def test_datas_especiais_alternam_entre_os_anos(plano):
    escolhas = _simular(plano, dt.date(2026, 1, 1), 4 * 365)
    natais = [c.ref for d, c in escolhas if (d.month, d.day) == (12, 25)]
    assert len(natais) == 4 and len(set(natais)) == 4  # 4 versículos de Natal, um por ano
    pascoas = [c.ref for _, c in escolhas if c.special_day == "pascoa"]
    assert len(set(pascoas)) == len(pascoas)


def test_rodizio_continua_do_ultimo_usado(plano):
    comuns = [e for e in plano if e.special_day is None]
    d = dt.date(2026, 11, 3)  # dia comum
    hist = [(d - dt.timedelta(days=1), comuns[10].ref)]
    assert choose_verse(d, plano, hist).ref == comuns[11].ref
    assert choose_verse(d, plano, []).ref == comuns[0].ref


def test_plano_pequeno_repete_o_mais_antigo():
    plano = [PlanEntry("JHN 3:16", "a", None), PlanEntry("PSA 23:1", "b", None)]
    hist = [(dt.date(2026, 11, 1), "JHN 3:16"), (dt.date(2026, 11, 2), "PSA 23:1")]
    assert choose_verse(dt.date(2026, 11, 3), plano, hist).ref == "JHN 3:16"


@pytest.mark.parametrize(
    "linha",
    ["Xyz 1.1,tema,", "Jo 3.16,tema,aniversario", "Sl 151,tema,"],
)
def test_csv_invalido(tmp_path, linha):
    p = tmp_path / "plano.csv"
    p.write_text(f"ref,tema,data_especial\n{linha}\n")
    with pytest.raises(PlanError):
        load_plan(p)


async def test_sincroniza_com_o_banco(migrated_db_url, plano):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.services.content_data import load_active_plan, sync_verse_plan

    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        await s.execute(text("DELETE FROM verse_plan"))
        await s.commit()
        r = await sync_verse_plan(s, plano)
        assert (r.inserted, r.updated, r.deactivated) == (len(plano), 0, 0)
        r = await sync_verse_plan(s, plano)  # idempotente
        assert (r.inserted, r.updated, r.deactivated) == (0, 0, 0)
        r = await sync_verse_plan(s, plano[1:])  # entrada removida do arquivo → desativada
        assert r.deactivated == 1
        assert await load_active_plan(s) == plano[1:]
    await engine.dispose()
