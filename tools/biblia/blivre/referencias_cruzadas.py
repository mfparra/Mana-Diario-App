"""Importa as referências cruzadas do OpenBible.info (CC BY) para `crossrefs.sqlite` (só o servidor usa).

Formato da fonte (TSV): `From Verse<TAB>To Verse<TAB>Votes`, com `Gen.1.1` e intervalos `John.1.1-John.1.3`.
A versificação é a mesma da BLIVRE (KJV/TR); referências inexistentes na BLIVRE são descartadas
(hoje só 3Jo 1.15) e linhas com votos ≤ 0 também.
"""

import hashlib
import io
import sqlite3
import zipfile
from dataclasses import dataclass
from pathlib import Path

from blivre.importar import verse_id

SOURCE_URL = "https://a.openbible.info/data/cross-references.zip"
ATTRIBUTION = (
    "Referências cruzadas: OpenBible.info (CC BY), https://www.openbible.info/labs/cross-references/"
)

# Abreviações do OpenBible.info na ordem canônica (= ordinal dos livros da BLIVRE).
OPENBIBLE_BOOKS = (  # noqa: SIM905 — mais legível que 66 strings
    "Gen Exod Lev Num Deut Josh Judg Ruth 1Sam 2Sam 1Kgs 2Kgs 1Chr 2Chr Ezra Neh Esth Job Ps Prov Eccl "
    "Song Isa Jer Lam Ezek Dan Hos Joel Amos Obad Jonah Mic Nah Hab Zeph Hag Zech Mal Matt Mark Luke John "
    "Acts Rom 1Cor 2Cor Gal Eph Phil Col 1Thess 2Thess 1Tim 2Tim Titus Phlm Heb Jas 1Pet 2Pet 1John 2John "
    "3John Jude Rev"
).split()
_ORDINAL = {b: i for i, b in enumerate(OPENBIBLE_BOOKS, start=1)}

SCHEMA = (
    "CREATE TABLE cross_references (from_id INTEGER NOT NULL, to_start_id INTEGER NOT NULL, "
    "to_end_id INTEGER NOT NULL, votes INTEGER NOT NULL, PRIMARY KEY (from_id, to_start_id, to_end_id))",
    "CREATE INDEX ix_cross_references_from_votes ON cross_references (from_id, votes DESC)",
    "CREATE TABLE metadata (key TEXT NOT NULL PRIMARY KEY, value TEXT NOT NULL)",
)


class CrossRefError(ValueError):
    pass


def openbible_to_id(ref: str) -> int:
    """`Gen.1.1` → 1001001."""
    try:
        book, chapter, verse = ref.split(".")
        return verse_id(_ORDINAL[book], int(chapter), int(verse))
    except (KeyError, ValueError) as exc:
        raise CrossRefError(f"referência OpenBible inválida: {ref!r}") from exc


@dataclass
class CrossRefReport:
    rows: int
    skipped_votes: int
    skipped_missing: int
    sha256: str


def build_crossrefs(zip_path: Path, blivre_path: Path, out_path: Path) -> CrossRefReport:
    sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    with zipfile.ZipFile(zip_path) as zf:
        name = next(n for n in zf.namelist() if n.endswith(".txt"))
        lines = io.TextIOWrapper(zf.open(name), encoding="utf-8").read().splitlines()
    header = lines[0]
    if not header.startswith("From Verse\tTo Verse\tVotes"):
        raise CrossRefError(f"cabeçalho inesperado: {header!r}")

    src = sqlite3.connect(f"file:{blivre_path}?mode=ro", uri=True)
    existing = {r[0] for r in src.execute("SELECT id FROM verses")}
    src.close()

    rows: dict[tuple[int, int, int], int] = {}
    skipped_votes = skipped_missing = 0
    for line in lines[1:]:
        if not line.strip():
            continue
        frm, to, votes_s = line.split("\t")
        votes = int(votes_s)
        if votes <= 0:
            skipped_votes += 1
            continue
        start, _, end = to.partition("-")
        ids = (openbible_to_id(frm), openbible_to_id(start), openbible_to_id(end or start))
        if any(i not in existing for i in ids) or ids[2] < ids[1]:
            skipped_missing += 1
            continue
        rows[ids] = max(votes, rows.get(ids, 0))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    try:
        for ddl in SCHEMA:
            con.execute(ddl)
        con.executemany("INSERT INTO cross_references VALUES (?,?,?,?)", [(*k, v) for k, v in rows.items()])
        con.executemany(
            "INSERT INTO metadata VALUES (?,?)",
            [
                ("source_url", SOURCE_URL),
                ("source_sha256", sha),
                ("source_header", header.split("#", 1)[-1].strip()),
                ("license", "CC BY"),
                ("attribution", ATTRIBUTION),
            ],
        )
        con.commit()
        con.execute("VACUUM")
    finally:
        con.close()
    tmp.replace(out_path)
    return CrossRefReport(len(rows), skipped_votes, skipped_missing, sha)
