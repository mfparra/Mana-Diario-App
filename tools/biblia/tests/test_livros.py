import zipfile

from blivre.livros import BOOKS
from blivre.usfm import parse_book
from tests.conftest import FONTE_ZIP


def test_canon():
    assert len(BOOKS) == 66
    assert len({b.usfm for b in BOOKS}) == 66
    assert len({b.abbrev_pt.casefold() for b in BOOKS}) == 66, "abreviações precisam ser únicas"
    assert sum(b.chapters for b in BOOKS) == 1189
    assert [b.ordinal for b in BOOKS] == list(range(1, 67))


def test_nomes_batem_com_a_fonte():
    by_usfm = {b.usfm: b for b in BOOKS}
    with zipfile.ZipFile(FONTE_ZIP) as zf:
        for name in zf.namelist():
            if name.endswith(".usfm"):
                parsed = parse_book(zf.read(name).decode("utf-8-sig"))
                assert by_usfm[parsed.usfm].name_pt == parsed.name
