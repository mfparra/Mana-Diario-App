"""Gera `blivre.sqlite` a partir do zip USFM da BLIVRE.

O schema segue exatamente o formato que o Room gera (ver `tools/biblia/SCHEMA.md`), porque o mesmo
arquivo é usado pelo servidor (somente leitura) e embarcado no app via `createFromAsset`.
"""

import hashlib
import re
import sqlite3
import zipfile
from dataclasses import dataclass
from pathlib import Path

from blivre.livros import BOOKS
from blivre.usfm import ParsedBook, parse_book

#: Versão do banco (= `version` do `@Database` do Room). Mude junto com o app.
SCHEMA_VERSION = 1

SCHEMA_DDL: tuple[str, ...] = (
    "CREATE TABLE IF NOT EXISTS `books` (`id` INTEGER NOT NULL, `usfm` TEXT NOT NULL, "
    "`name_pt` TEXT NOT NULL, `abbrev_pt` TEXT NOT NULL, `testament` TEXT NOT NULL, "
    "`ordinal` INTEGER NOT NULL, `chapters` INTEGER NOT NULL, PRIMARY KEY(`id`))",
    "CREATE UNIQUE INDEX IF NOT EXISTS `index_books_usfm` ON `books` (`usfm`)",
    "CREATE TABLE IF NOT EXISTS `verses` (`id` INTEGER NOT NULL, `book_id` INTEGER NOT NULL, "
    "`chapter` INTEGER NOT NULL, `verse` INTEGER NOT NULL, `text` TEXT NOT NULL, PRIMARY KEY(`id`), "
    "FOREIGN KEY(`book_id`) REFERENCES `books`(`id`) ON UPDATE NO ACTION ON DELETE NO ACTION )",
    "CREATE UNIQUE INDEX IF NOT EXISTS `index_verses_book_id_chapter_verse` "
    "ON `verses` (`book_id`, `chapter`, `verse`)",
    "CREATE VIRTUAL TABLE IF NOT EXISTS `verses_fts` USING FTS4(`text` TEXT NOT NULL, "
    "tokenize=unicode61 `remove_diacritics=1`, content=`verses`)",
    "CREATE TABLE IF NOT EXISTS `footnotes` (`id` INTEGER NOT NULL, `verse_id` INTEGER NOT NULL, "
    "`ordinal` INTEGER NOT NULL, `position` INTEGER NOT NULL, `kind` TEXT NOT NULL, `quote` TEXT, "
    "`text` TEXT NOT NULL, PRIMARY KEY(`id`), FOREIGN KEY(`verse_id`) REFERENCES `verses`(`id`) "
    "ON UPDATE NO ACTION ON DELETE NO ACTION )",
    "CREATE INDEX IF NOT EXISTS `index_footnotes_verse_id` ON `footnotes` (`verse_id`)",
    "CREATE TABLE IF NOT EXISTS `superscriptions` (`book_id` INTEGER NOT NULL, `chapter` INTEGER NOT NULL, "
    "`text` TEXT NOT NULL, PRIMARY KEY(`book_id`, `chapter`), FOREIGN KEY(`book_id`) REFERENCES "
    "`books`(`id`) ON UPDATE NO ACTION ON DELETE NO ACTION )",
    "CREATE TABLE IF NOT EXISTS `metadata` (`key` TEXT NOT NULL, `value` TEXT NOT NULL, PRIMARY KEY(`key`))",
)

SOURCE_ID = "porbr2018"
SOURCE_URL = "https://ebible.org/Scriptures/porbr2018_usfm.zip"
ATTRIBUTION = (
    "Todas as Escrituras em português citadas são da Bíblia Livre (BLIVRE), Copyright © Diego Santos, "
    "Mario Sérgio, e Marco Teles, http://sites.google.com/site/biblialivre/ - fevereiro de 2018. "
    "Licença Creative Commons Atribuição 4.0 Brasil (http://creativecommons.org/licenses/by/4.0/br/)."
)


def verse_id(book_ordinal: int, chapter: int, verse: int) -> int:
    """ID estável e legível: 43003016 = João 3.16."""
    return book_ordinal * 1_000_000 + chapter * 1_000 + verse


@dataclass
class ImportReport:
    books: int
    verses: int
    source_verse_markers: int
    footnotes: int
    superscriptions: int
    sha256: str


class BlivreImportError(RuntimeError):
    pass


def read_source(zip_path: Path) -> tuple[list[ParsedBook], int]:
    """Lê os 66 livros do zip (na ordem canônica) e conta os marcadores `\\v` brutos da fonte."""
    by_usfm: dict[str, ParsedBook] = {}
    markers = 0
    with zipfile.ZipFile(zip_path) as zf:
        for name in sorted(zf.namelist()):
            if not name.endswith(".usfm"):
                continue
            content = zf.read(name).decode("utf-8-sig")
            markers += len(re.findall(r"^\\v\s", content, re.M))
            book = parse_book(content)
            by_usfm[book.usfm] = book
    expected = [b.usfm for b in BOOKS]
    if sorted(by_usfm) != sorted(expected):
        raise BlivreImportError(f"Livros na fonte diferem do cânon: {sorted(set(by_usfm) ^ set(expected))}")
    return [by_usfm[u] for u in expected], markers


def build_database(zip_path: Path, out_path: Path) -> ImportReport:
    books, markers = read_source(zip_path)
    sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    try:
        con.execute("PRAGMA journal_mode=DELETE")
        for ddl in SCHEMA_DDL:
            con.execute(ddl)
        n_verses = n_notes = n_sup = 0
        note_id = 0
        for meta, parsed in zip(BOOKS, books, strict=True):
            if parsed.chapters != meta.chapters:
                raise BlivreImportError(
                    f"{meta.usfm}: {parsed.chapters} capítulos na fonte, esperado {meta.chapters}"
                )
            con.execute(
                "INSERT INTO books VALUES (?,?,?,?,?,?,?)",
                (
                    meta.ordinal,
                    meta.usfm,
                    meta.name_pt,
                    meta.abbrev_pt,
                    meta.testament,
                    meta.ordinal,
                    meta.chapters,
                ),
            )
            seen: set[tuple[int, int]] = set()
            for v in parsed.verses:
                key = (v.chapter, v.verse)
                if key in seen:
                    raise BlivreImportError(f"{meta.usfm} {key}: versículo duplicado")
                seen.add(key)
                if not v.text:
                    raise BlivreImportError(f"{meta.usfm} {key}: versículo vazio")
                vid = verse_id(meta.ordinal, v.chapter, v.verse)
                con.execute(
                    "INSERT INTO verses VALUES (?,?,?,?,?)", (vid, meta.ordinal, v.chapter, v.verse, v.text)
                )
                n_verses += 1
                for fn in v.footnotes:
                    note_id += 1
                    con.execute(
                        "INSERT INTO footnotes VALUES (?,?,?,?,?,?,?)",
                        (note_id, vid, fn.ordinal, fn.position, fn.kind, fn.quote, fn.text),
                    )
                    n_notes += 1
            for chapter, text in sorted(parsed.superscriptions.items()):
                con.execute("INSERT INTO superscriptions VALUES (?,?,?)", (meta.ordinal, chapter, text))
                n_sup += 1
        con.execute("INSERT INTO verses_fts(verses_fts) VALUES ('rebuild')")
        con.executemany(
            "INSERT INTO metadata VALUES (?,?)",
            [
                ("source_id", SOURCE_ID),
                ("source_url", SOURCE_URL),
                ("source_sha256", sha),
                ("translation", "Bíblia Livre (BLIVRE), Textus Receptus, fevereiro de 2018"),
                ("license", "CC BY 4.0 Brasil"),
                ("attribution", ATTRIBUTION),
            ],
        )
        if n_verses != markers:
            raise BlivreImportError(f"{n_verses} versículos importados, {markers} marcadores \\v na fonte")
        con.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        con.commit()
        con.execute("VACUUM")
    finally:
        con.close()
    tmp.replace(out_path)
    return ImportReport(len(books), n_verses, markers, n_notes, n_sup, sha)
