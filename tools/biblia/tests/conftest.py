import sqlite3
from pathlib import Path

import pytest

from blivre.importar import ImportReport, build_database

FONTE_ZIP = Path(__file__).resolve().parents[1] / "fonte" / "porbr2018_usfm.zip"


@pytest.fixture(scope="session")
def built(tmp_path_factory) -> tuple[Path, ImportReport]:
    out = tmp_path_factory.mktemp("blivre") / "blivre.sqlite"
    report = build_database(FONTE_ZIP, out)
    return out, report


@pytest.fixture(scope="session")
def db(built):
    con = sqlite3.connect(f"file:{built[0]}?mode=ro", uri=True)
    yield con
    con.close()
