import pytest

from blivre.livros import BOOKS
from blivre.referencias_cruzadas import OPENBIBLE_BOOKS, CrossRefError, openbible_to_id


def test_66_livros_na_ordem_canonica():
    assert len(OPENBIBLE_BOOKS) == len(BOOKS) == 66


@pytest.mark.parametrize(
    ("ref", "vid"),
    [("Gen.1.1", 1001001), ("John.3.16", 43003016), ("Ps.119.176", 19119176), ("Rev.22.21", 66022021),
     ("1John.4.8", 62004008), ("Phlm.1.6", 57001006)],
)  # fmt: skip
def test_conversao(ref, vid):
    assert openbible_to_id(ref) == vid


@pytest.mark.parametrize("ref", ["Xyz.1.1", "Gen.1", "Gen.a.1"])
def test_invalida(ref):
    with pytest.raises(CrossRefError):
        openbible_to_id(ref)
