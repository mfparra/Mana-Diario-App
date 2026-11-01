import pytest

from blivre.usfm import UsfmError, clean_verse_text, parse_book


def test_add_mantem_palavras():
    assert clean_verse_text(r"a seu \add devido\add* tempo")[0] == "a seu devido tempo"
    assert clean_verse_text(r"Ungido, \add dizendo\add* :")[0] == "Ungido, dizendo:"


def test_nota_no_meio():
    text, notes = clean_verse_text(r"como deuses, \f + \fr 3:5 \ft Ou: sereis como Deus \f* sabendo o bem.")
    assert text == "como deuses, sabendo o bem."
    assert notes[0].text == "Ou: sereis como Deus"
    assert notes[0].position == len("como deuses,")
    assert notes[0].quote is None


def test_nota_com_fq_antes_de_pontuacao():
    text, notes = clean_verse_text(r"eram muitos \f + \fr 1:5 \fq muitos \ft lit. fortes \f* .")
    assert text == "eram muitos."  # o espaço antes do ponto só existia por causa da nota
    assert notes[0].quote == "muitos"
    assert notes[0].text == "lit. fortes"


def test_rq_no_fim():
    text, notes = clean_verse_text(r"Deus conosco. \rq Isaías 7:14 \rq*")
    assert text == "Deus conosco."
    assert (notes[0].kind, notes[0].text) == ("quote_source", "Isaías 7:14")


def test_marcador_desconhecido_falha():
    with pytest.raises(UsfmError):
        clean_verse_text(r"texto \wj palavras\wj*")
    with pytest.raises(UsfmError):
        parse_book("\\id GEN x\n\\h Gênesis\n\\toc3 Gn\n\\c 1\n\\q1 poesia\n")


def test_parse_book_minimo():
    b = parse_book(
        "\\id PSA Bíblia\n\\h Salmos\n\\toc3 Sl\n\\c 3\n\\d Salmo de Davi:\n\\p\n\\v 1 Ah SENHOR.\n"
    )
    assert (b.usfm, b.name, b.abbrev, b.chapters) == ("PSA", "Salmos", "Sl", 3)
    assert b.superscriptions == {3: "Salmo de Davi:"}
    assert b.verses[0].text == "Ah SENHOR."
