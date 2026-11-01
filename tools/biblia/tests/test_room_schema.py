import copy
import json
from pathlib import Path

import pytest

from blivre.importar import SCHEMA_VERSION
from blivre.room_schema import compare

ANDROID_SCHEMAS = (
    Path(__file__).resolve().parents[3]
    / "android/app/schemas/com.marcosparra.manadiario.core.bible.BlivreDatabase"
)


def _f(col: str, affinity: str, not_null: bool = True) -> dict:
    return {"fieldPath": col, "columnName": col, "affinity": affinity, "notNull": not_null}


# Espelho do que o Room exporta para as entidades descritas em tools/biblia/SCHEMA.md.
ROOM_ESPERADO = {
    "formatVersion": 1,
    "database": {
        "version": SCHEMA_VERSION,
        "entities": [
            {
                "tableName": "books",
                "fields": [
                    _f("id", "INTEGER"),
                    _f("usfm", "TEXT"),
                    _f("name_pt", "TEXT"),
                    _f("abbrev_pt", "TEXT"),
                    _f("testament", "TEXT"),
                    _f("ordinal", "INTEGER"),
                    _f("chapters", "INTEGER"),
                ],
                "primaryKey": {"autoGenerate": False, "columnNames": ["id"]},
                "indices": [{"name": "index_books_usfm", "unique": True, "columnNames": ["usfm"]}],
                "foreignKeys": [],
            },
            {
                "tableName": "verses",
                "fields": [
                    _f("id", "INTEGER"),
                    _f("book_id", "INTEGER"),
                    _f("chapter", "INTEGER"),
                    _f("verse", "INTEGER"),
                    _f("text", "TEXT"),
                ],
                "primaryKey": {"autoGenerate": False, "columnNames": ["id"]},
                "indices": [
                    {
                        "name": "index_verses_book_id_chapter_verse",
                        "unique": True,
                        "columnNames": ["book_id", "chapter", "verse"],
                    }
                ],
                "foreignKeys": [
                    {
                        "table": "books",
                        "onDelete": "NO ACTION",
                        "onUpdate": "NO ACTION",
                        "columns": ["book_id"],
                        "referencedColumns": ["id"],
                    }
                ],
            },
            {
                "tableName": "verses_fts",
                "ftsVersion": "FTS4",
                "createSql": "CREATE VIRTUAL TABLE IF NOT EXISTS `${TABLE_NAME}` "
                "USING FTS4(`text` TEXT NOT NULL, "
                "tokenize=unicode61 `remove_diacritics=1`, content=`verses`)",
                "fields": [_f("text", "TEXT")],
            },
            {
                "tableName": "footnotes",
                "fields": [
                    _f("id", "INTEGER"),
                    _f("verse_id", "INTEGER"),
                    _f("ordinal", "INTEGER"),
                    _f("position", "INTEGER"),
                    _f("kind", "TEXT"),
                    _f("quote", "TEXT", False),
                    _f("text", "TEXT"),
                ],
                "primaryKey": {"autoGenerate": False, "columnNames": ["id"]},
                "indices": [
                    {"name": "index_footnotes_verse_id", "unique": False, "columnNames": ["verse_id"]}
                ],
                "foreignKeys": [{"table": "verses", "columns": ["verse_id"], "referencedColumns": ["id"]}],
            },
            {
                "tableName": "superscriptions",
                "fields": [_f("book_id", "INTEGER"), _f("chapter", "INTEGER"), _f("text", "TEXT")],
                "primaryKey": {"autoGenerate": False, "columnNames": ["book_id", "chapter"]},
                "indices": [],
                "foreignKeys": [{"table": "books", "columns": ["book_id"], "referencedColumns": ["id"]}],
            },
            {
                "tableName": "metadata",
                "fields": [_f("key", "TEXT"), _f("value", "TEXT")],
                "primaryKey": {"autoGenerate": False, "columnNames": ["key"]},
                "indices": [],
                "foreignKeys": [],
            },
        ],
    },
}


def _write(tmp_path, schema) -> Path:
    p = tmp_path / "room.json"
    p.write_text(json.dumps(schema))
    return p


def test_banco_bate_com_o_schema_room_esperado(built, tmp_path):
    assert compare(built[0], _write(tmp_path, ROOM_ESPERADO)) == []


def test_comparador_detecta_divergencias(built, tmp_path):
    ruim = copy.deepcopy(ROOM_ESPERADO)
    ruim["database"]["version"] = 99
    ruim["database"]["entities"][0]["fields"][1]["notNull"] = False
    ruim["database"]["entities"][1]["indices"] = []
    problems = compare(built[0], _write(tmp_path, ruim))
    assert any("user_version" in p for p in problems)
    assert any("books.usfm: NOT NULL" in p for p in problems)
    assert any("verses: índices" in p for p in problems)


@pytest.mark.skipif(not ANDROID_SCHEMAS.exists(), reason="app Android ainda não exporta o schema (Fase 5)")
def test_banco_bate_com_schema_exportado_pelo_app(built):
    room_json = ANDROID_SCHEMAS / f"{SCHEMA_VERSION}.json"
    assert room_json.exists(), f"Schema do Room versão {SCHEMA_VERSION} não encontrado"
    assert compare(built[0], room_json) == []
