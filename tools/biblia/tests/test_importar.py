import hashlib
import re
import zipfile

import pytest

from blivre.importar import SCHEMA_VERSION, verse_id
from blivre.livros import BOOKS
from tests.conftest import FONTE_ZIP


def test_zip_confere_com_sha256sums():
    linha = (FONTE_ZIP.parent / "SHA256SUMS").read_text().split()
    assert linha[1] == FONTE_ZIP.name
    assert hashlib.sha256(FONTE_ZIP.read_bytes()).hexdigest() == linha[0]


def test_66_livros(db):
    rows = db.execute("SELECT id, usfm, ordinal, testament, chapters FROM books ORDER BY id").fetchall()
    assert len(rows) == 66
    assert [r[1] for r in rows] == [b.usfm for b in BOOKS]
    assert sum(1 for r in rows if r[3] == "OT") == 39
    assert sum(r[4] for r in rows) == 1189


def test_contagem_de_versiculos_igual_a_fonte(db, built):
    markers = 0
    with zipfile.ZipFile(FONTE_ZIP) as zf:
        for name in zf.namelist():
            if name.endswith(".usfm"):
                markers += len(re.findall(r"^\\v\s", zf.read(name).decode("utf-8-sig"), re.M))
    (n,) = db.execute("SELECT count(*) FROM verses").fetchone()
    assert n == markers == built[1].verses == 31102


def test_capitulos_batem_com_os_versiculos(db):
    for book_id, chapters in db.execute("SELECT id, chapters FROM books"):
        (max_ch,) = db.execute("SELECT max(chapter) FROM verses WHERE book_id=?", (book_id,)).fetchone()
        assert max_ch == chapters


# Os 5 primeiros conferidos com a página da eBible.org (porbr2018); os demais exercitam marcadores.
VERSICULOS_CONHECIDOS = [
    ("GEN", 1, 1, "No princípio criou Deus os céus e a terra."),
    ("PSA", 23, 1, "O SENHOR é meu pastor, nada me faltará."),
    (
        "MAT",
        6,
        33,
        "Mas buscai primeiramente o Reino de Deus e a sua justiça, e todas estas coisas vos serão "
        "acrescentadas.",
    ),
    (
        "JHN",
        3,
        16,
        "Porque Deus amou ao mundo de tal maneira, que deu o seu Filho unigênito; para que todo "
        "aquele que nele crê não pereça, mas tenha a vida eterna.",
    ),
    (
        "ROM",
        8,
        28,
        "E sabemos que todas as coisas juntamente contribuem para o bem daqueles que amam a Deus, "
        "dos que são chamados segundo o seu propósito.",
    ),
    # \f nota removida do meio do versículo
    (
        "GEN",
        3,
        5,
        "Mas Deus sabe que no dia que comerdes dele, vossos olhos serão abertos, e sereis como "
        "deuses, sabendo o bem e o mal.",
    ),
    # \add mantém a palavra, sem colar na seguinte
    (
        "PSA",
        1,
        3,
        "Porque ele será como uma árvore, plantada junto a ribeiros de águas, que dá fruto a seu "
        "devido tempo, e suas folhas não caem; e tudo quanto fizer prosperará.",
    ),
    # \add seguido de pontuação
    (
        "PSA",
        2,
        2,
        "Os reis da terra se levantam, e os governantes tomam conselhos reunidos contra o SENHOR, "
        "e contra seu Ungido, dizendo:",
    ),
    # \rq removido do fim
    (
        "MAT",
        1,
        23,
        "Eis que a virgem conceberá, e dará à luz um filho, e chamarão seu nome Emanuel, que "
        "traduzido é: Deus conosco.",
    ),
    (
        "REV",
        22,
        21,
        "A graça do nosso Senhor Jesus Cristo seja com todos vós. Amém!",
    ),  # conferido no USFM bruto
]


@pytest.mark.parametrize(("usfm", "ch", "v", "esperado"), VERSICULOS_CONHECIDOS)
def test_versiculos_conhecidos(db, usfm, ch, v, esperado):
    row = db.execute(
        "SELECT v.text, v.id FROM verses v JOIN books b ON b.id=v.book_id "
        "WHERE b.usfm=? AND v.chapter=? AND v.verse=?",
        (usfm, ch, v),
    ).fetchone()
    assert row[0] == esperado
    ordinal = next(b.ordinal for b in BOOKS if b.usfm == usfm)
    assert row[1] == verse_id(ordinal, ch, v)


def test_nenhum_marcador_sobrou(db):
    assert db.execute("SELECT count(*) FROM verses WHERE text LIKE '%\\%' OR text = ''").fetchone() == (0,)
    assert db.execute("SELECT count(*) FROM footnotes WHERE text LIKE '%\\%'").fetchone() == (0,)


def test_notas_e_titulos(db):
    nota = db.execute("SELECT kind, quote, text, position FROM footnotes WHERE verse_id=1003005").fetchone()
    assert nota == (
        "note",
        None,
        "Ou: sereis como Deus",
        len("Mas Deus sabe que no dia que comerdes dele, vossos olhos serão abertos, e sereis como deuses,"),
    )
    assert db.execute("SELECT kind, text FROM footnotes WHERE verse_id=40001023").fetchone() == (
        "quote_source",
        "Isaías 7:14",
    )
    assert db.execute("SELECT text FROM superscriptions WHERE book_id=19 AND chapter=23").fetchone() == (
        "Salmo de Davi:",
    )


def test_busca_sem_acento_encontra_texto_acentuado(db):
    com = db.execute("SELECT count(*) FROM verses_fts WHERE verses_fts MATCH 'coração'").fetchone()[0]
    sem = db.execute("SELECT count(*) FROM verses_fts WHERE verses_fts MATCH 'coracao'").fetchone()[0]
    assert com == sem > 100
    (rowid,) = db.execute(
        "SELECT rowid FROM verses_fts WHERE verses_fts MATCH 'unigenito AND mundo AND amou'"
    ).fetchone()
    assert rowid == 43003016


def test_user_version_e_metadados(db):
    assert db.execute("PRAGMA user_version").fetchone() == (SCHEMA_VERSION,)
    meta = dict(db.execute("SELECT key, value FROM metadata"))
    assert meta["license"] == "CC BY 4.0 Brasil"
    assert "Bíblia Livre (BLIVRE)" in meta["attribution"]
    assert meta["source_sha256"] == hashlib.sha256(FONTE_ZIP.read_bytes()).hexdigest()
