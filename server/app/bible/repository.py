"""Leitura do `blivre.sqlite` (somente leitura). Única fonte de texto bíblico do servidor.

Os IDs dos versículos codificam livro/capítulo/versículo (`43003016` = João 3.16), então qualquer
intervalo — inclusive entre capítulos — vira um único `BETWEEN`.
"""

import sqlite3
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from blivre import Reference, VerseRange, book_by_usfm, format_canonical, format_reference, parse_reference

from app.core.config import get_settings


class BibleError(LookupError):
    """Referência que não existe na BLIVRE."""


@dataclass(frozen=True)
class VerseText:
    book: str  # USFM
    chapter: int
    verse: int
    text: str


@dataclass(frozen=True)
class Passage:
    reference: Reference
    verses: tuple[VerseText, ...]

    @property
    def text(self) -> str:
        """Texto corrido (sem números de versículo)."""
        return " ".join(v.text for v in self.verses)

    @property
    def display(self) -> str:
        return format_reference(self.reference)

    @property
    def canonical(self) -> str:
        return format_canonical(self.reference)


def _vid(ordinal: int, chapter: int, verse: int) -> int:
    return ordinal * 1_000_000 + chapter * 1_000 + verse


def _bounds(ordinal: int, r: VerseRange) -> tuple[int, int]:
    if r.whole_chapters:
        return _vid(ordinal, r.chapter, 0), _vid(ordinal, r.chapter_end, 999)
    assert r.verse_start is not None and r.verse_end is not None
    return _vid(ordinal, r.chapter, r.verse_start), _vid(ordinal, r.chapter_end, r.verse_end)


class BibleRepository:
    def __init__(self, path: str | Path):
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"blivre.sqlite não encontrado em {path}")
        self._con = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True, check_same_thread=False)
        self._lock = threading.Lock()

    def close(self) -> None:
        self._con.close()

    def _query(self, sql: str, params: tuple) -> list[tuple]:
        with self._lock:
            return self._con.execute(sql, params).fetchall()

    @staticmethod
    def _ref(ref: Reference | str) -> Reference:
        return parse_reference(ref) if isinstance(ref, str) else ref

    def exists(self, ref: Reference | str) -> bool:
        """True se todo trecho da referência existe (início e fim de cada intervalo)."""
        try:
            ref = self._ref(ref)
        except ValueError:
            return False
        ordinal = book_by_usfm(ref.book).ordinal
        for r in ref.ranges:
            lo, hi = _bounds(ordinal, r)
            if r.whole_chapters:
                rows = self._query(
                    "SELECT count(DISTINCT chapter) FROM verses WHERE id BETWEEN ? AND ?", (lo, hi)
                )
                if rows[0][0] != r.chapter_end - r.chapter + 1:
                    return False
            else:
                rows = self._query("SELECT count(*) FROM verses WHERE id IN (?, ?)", (lo, hi))
                if rows[0][0] != (1 if lo == hi else 2):
                    return False
        return True

    def get_passage(self, ref: Reference | str) -> Passage:
        ref = self._ref(ref)
        if not self.exists(ref):
            raise BibleError(f"Referência inexistente na BLIVRE: {format_reference(ref)}")
        ordinal = book_by_usfm(ref.book).ordinal
        verses: list[VerseText] = []
        for r in ref.ranges:
            lo, hi = _bounds(ordinal, r)
            rows = self._query(
                "SELECT chapter, verse, text FROM verses WHERE id BETWEEN ? AND ? ORDER BY id", (lo, hi)
            )
            verses.extend(VerseText(ref.book, c, v, t) for c, v, t in rows)
        return Passage(ref, tuple(verses))

    def get_text(self, ref: Reference | str) -> str:
        return self.get_passage(ref).text

    def metadata(self) -> dict[str, str]:
        return dict(self._query("SELECT key, value FROM metadata", ()))


@lru_cache
def get_bible() -> BibleRepository:
    return BibleRepository(get_settings().blivre_sqlite_path)
