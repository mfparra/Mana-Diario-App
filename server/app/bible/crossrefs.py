"""Candidatos de leitura complementar (DECISOES P9) a partir das referências cruzadas do OpenBible.info.

O servidor oferece até N candidatos válidos na BLIVRE; a LLM escolhe um pelo índice; o servidor valida.
Regras de seleção:
- soma os votos de todos os versículos da passagem-base (ex.: 1Co 13.4-7);
- descarta alvos que se sobrepõem à própria passagem;
- no máximo `per_book` candidatos do mesmo livro (variedade);
- ordena por votos (desc) e, em empate, pela ordem canônica (determinístico).
"""

import sqlite3
import threading
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from blivre import BOOKS, Reference, VerseRange, parse_reference

from app.bible.repository import BibleRepository, get_bible
from app.core.config import get_settings

_BY_ORDINAL = {b.ordinal: b for b in BOOKS}


def _split(vid: int) -> tuple[int, int, int]:
    return vid // 1_000_000, (vid // 1_000) % 1_000, vid % 1_000


def _to_reference(start_id: int, end_id: int) -> Reference:
    ob, c1, v1 = _split(start_id)
    _, c2, v2 = _split(end_id)
    return Reference(_BY_ORDINAL[ob].usfm, (VerseRange(c1, v1, c2, v2),))


class CrossReferenceRepository:
    def __init__(self, path: str | Path, bible: BibleRepository):
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"crossrefs.sqlite não encontrado em {path}")
        self._con = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True, check_same_thread=False)
        self._lock = threading.Lock()
        self._bible = bible

    def close(self) -> None:
        self._con.close()

    def candidates(
        self, ref: Reference | str, limit: int = 8, min_votes: int = 3, per_book: int = 3
    ) -> list[Reference]:
        base = parse_reference(ref) if isinstance(ref, str) else ref
        passage = self._bible.get_passage(base)  # valida que a base existe
        ordinal = next(b.ordinal for b in BOOKS if b.usfm == base.book)
        base_ids = [ordinal * 1_000_000 + v.chapter * 1_000 + v.verse for v in passage.verses]
        lo, hi = min(base_ids), max(base_ids)

        marks = ",".join("?" * len(base_ids))
        with self._lock:
            rows = self._con.execute(
                f"SELECT to_start_id, to_end_id, sum(votes) FROM cross_references WHERE from_id IN ({marks}) "
                "GROUP BY to_start_id, to_end_id",
                base_ids,
            ).fetchall()

        ranked = sorted(
            ((s, e, v) for s, e, v in rows if v >= min_votes and (e < lo or s > hi)),
            key=lambda r: (-r[2], r[0], r[1]),
        )
        out: list[Reference] = []
        per_book_count: dict[int, int] = defaultdict(int)
        taken: list[tuple[int, int]] = []
        for start, end, _ in ranked:
            book = start // 1_000_000
            if per_book_count[book] >= per_book:
                continue
            if any(not (end < s or start > e) for s, e in taken):  # sobrepõe candidato já escolhido
                continue
            cand = _to_reference(start, end)
            if not self._bible.exists(cand):
                continue
            out.append(cand)
            taken.append((start, end))
            per_book_count[book] += 1
            if len(out) == limit:
                break
        return out

    def metadata(self) -> dict[str, str]:
        with self._lock:
            return dict(self._con.execute("SELECT key, value FROM metadata").fetchall())


@lru_cache
def get_crossrefs() -> CrossReferenceRepository:
    return CrossReferenceRepository(get_settings().crossrefs_sqlite_path, get_bible())
