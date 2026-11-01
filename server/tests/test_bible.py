from pathlib import Path

import pytest
from blivre.importar import build_database

from app.bible.repository import BibleError, BibleRepository

FONTE = Path(__file__).resolve().parents[2] / "tools/biblia/fonte/porbr2018_usfm.zip"


@pytest.fixture(scope="module")
def bible(tmp_path_factory):
    db = tmp_path_factory.mktemp("blivre") / "blivre.sqlite"
    build_database(FONTE, db)
    repo = BibleRepository(db)
    yield repo
    repo.close()


def test_versiculo(bible):
    p = bible.get_passage("Jo 3.16")
    assert p.text.startswith("Porque Deus amou ao mundo de tal maneira")
    assert (p.display, p.canonical) == ("João 3.16", "JHN 3:16")
    assert [(v.chapter, v.verse) for v in p.verses] == [(3, 16)]


def test_intervalo(bible):
    p = bible.get_passage("1Co 13.4-7")
    assert [v.verse for v in p.verses] == [4, 5, 6, 7]
    assert p.text == " ".join(v.text for v in p.verses)


def test_intervalo_entre_capitulos(bible):
    p = bible.get_passage("Gn 1.31-2.3")
    assert [(v.chapter, v.verse) for v in p.verses] == [(1, 31), (2, 1), (2, 2), (2, 3)]


def test_capitulo_inteiro(bible):
    p = bible.get_passage("Sl 23")
    assert [v.verse for v in p.verses] == [1, 2, 3, 4, 5, 6]
    assert len(bible.get_passage("Sl 119").verses) == 176


def test_lista_e_forma_canonica(bible):
    p = bible.get_passage("JHN 3:16; 14:6")
    assert [(v.chapter, v.verse) for v in p.verses] == [(3, 16), (14, 6)]
    assert bible.get_text("Jo 3:16,18").count(" ") > 20


@pytest.mark.parametrize(
    ("ref", "ok"),
    [
        ("Jo 3.16", True),
        ("Jo 3.36", True),
        ("Jo 3.37", False),  # João 3 tem 36 versículos
        ("Jo 3.30-40", False),
        ("Sl 117", True),
        ("Sl 1-150", True),
        ("Jd 25", True),
        ("Jd 26", False),
        ("Xyz 1.1", False),  # livro inválido não levanta, só retorna False
        ("Ml 4.6", True),
    ],
)
def test_exists(bible, ref, ok):
    assert bible.exists(ref) is ok


def test_referencia_inexistente_levanta(bible):
    with pytest.raises(BibleError):
        bible.get_text("Jo 3.37")


def test_metadados(bible):
    assert bible.metadata()["license"] == "CC BY 4.0 Brasil"


def test_arquivo_ausente(tmp_path):
    with pytest.raises(FileNotFoundError):
        BibleRepository(tmp_path / "nada.sqlite")
