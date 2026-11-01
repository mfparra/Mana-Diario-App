from pathlib import Path

import pytest
from blivre import format_reference, parse_reference
from blivre.importar import build_database
from blivre.referencias_cruzadas import build_crossrefs

from app.bible.crossrefs import CrossReferenceRepository
from app.bible.repository import BibleRepository

FONTE = Path(__file__).resolve().parents[2] / "tools/biblia/fonte"

# 50 versículos muito usados em devocionais (só referências; o texto vem da BLIVRE).
AMOSTRA = """
Gn 1.1; Gn 1.27; Gn 50.20; Ex 14.14; Dt 31.6; Js 1.9; 1Sm 16.7; 2Cr 7.14; Ne 8.10; Jó 19.25;
Sl 23.1; Sl 27.1; Sl 37.4; Sl 46.1; Sl 46.10; Sl 51.10; Sl 91.1; Sl 119.105; Sl 121.1; Sl 139.14;
Pv 3.5; Pv 16.3; Ec 3.1; Is 26.3; Is 40.31; Is 41.10; Is 53.5; Jr 29.11; Lm 3.22; Mq 6.8;
Mt 5.14; Mt 6.33; Mt 11.28; Mt 28.19; Jo 3.16; Jo 14.6; Jo 15.5; Rm 8.28; Rm 12.2; 1Co 13.4;
2Co 5.17; Gl 5.22; Ef 2.8; Fp 4.6; Fp 4.13; Cl 3.23; Hb 11.1; Tg 1.5; 1Pe 5.7; 1Jo 4.8
""".replace("\n", " ")
VERSICULOS = [r.strip() for r in AMOSTRA.split(";") if r.strip()]


@pytest.fixture(scope="module")
def repos(tmp_path_factory):
    d = tmp_path_factory.mktemp("dados")
    build_database(FONTE / "porbr2018_usfm.zip", d / "blivre.sqlite")
    report = build_crossrefs(
        FONTE / "openbible_cross-references.zip", d / "blivre.sqlite", d / "crossrefs.sqlite"
    )
    bible = BibleRepository(d / "blivre.sqlite")
    xr = CrossReferenceRepository(d / "crossrefs.sqlite", bible)
    yield bible, xr, report
    xr.close()
    bible.close()


def test_importacao(repos):
    _, xr, report = repos
    assert report.rows > 300_000
    assert report.skipped_missing == 5  # 3Jo 1.15 não existe na BLIVRE
    assert xr.metadata()["license"] == "CC BY"


def test_amostra_tem_50_versiculos():
    assert len(VERSICULOS) == 50


@pytest.mark.parametrize("ref", VERSICULOS)
def test_pelo_menos_3_candidatos_validos(repos, ref):
    bible, xr, _ = repos
    cands = xr.candidates(ref)
    assert len(cands) >= 3, f"{ref}: {[format_reference(c) for c in cands]}"
    base = parse_reference(ref)
    for c in cands:
        assert bible.exists(c)
        assert c != base


def test_regras_de_selecao(repos):
    _, xr, _ = repos
    cands = xr.candidates("1Co 13.4-7", limit=8, per_book=2)
    assert 3 <= len(cands) <= 8
    livros = [c.book for c in cands]
    assert all(livros.count(b) <= 2 for b in livros)
    for c in cands:  # nenhum candidato dentro da própria passagem
        r = c.ranges[0]
        assert not (c.book == "1CO" and r.chapter == 13 and 4 <= (r.verse_start or 0) <= 7)
    assert xr.candidates("Jo 3.16") == xr.candidates("Jo 3.16")  # determinístico
