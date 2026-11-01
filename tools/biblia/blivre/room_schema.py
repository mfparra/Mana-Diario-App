"""Compara o `blivre.sqlite` gerado com o schema JSON exportado pelo Room (`exportSchema = true`).

O Room, ao abrir um banco de `createFromAsset`, valida tabelas, colunas (afinidade, NOT NULL, PK),
índices e chaves estrangeiras. Se algo divergir, o app quebra em tempo de execução — por isso
este comparador roda nos testes assim que o JSON existir em
`android/app/schemas/com.marcosparra.manadiario.core.bible.BlivreDatabase/<versão>.json`.
"""

import json
import sqlite3
from pathlib import Path


def _table_columns(con: sqlite3.Connection, table: str) -> dict[str, tuple[str, bool, int]]:
    return {r[1]: (r[2].upper(), bool(r[3]), r[5]) for r in con.execute(f"PRAGMA table_info(`{table}`)")}


def _indices(con: sqlite3.Connection, table: str) -> dict[str, tuple[bool, list[str]]]:
    out = {}
    for _, name, unique, origin, _ in con.execute(f"PRAGMA index_list(`{table}`)"):
        if origin == "c":  # criados com CREATE INDEX (o Room ignora os automáticos)
            cols = [r[2] for r in con.execute(f"PRAGMA index_info(`{name}`)")]
            out[name] = (bool(unique), cols)
    return out


def compare(db_path: Path, room_json: Path) -> list[str]:
    """Devolve a lista de divergências (vazia = compatível)."""
    schema = json.loads(room_json.read_text())["database"]
    problems: list[str] = []
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        (user_version,) = con.execute("PRAGMA user_version").fetchone()
        if user_version != schema["version"]:
            problems.append(f"user_version {user_version} ≠ versão do Room {schema['version']}")
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for entity in schema["entities"]:
            name = entity["tableName"]
            if name not in tables:
                problems.append(f"tabela ausente: {name}")
                continue
            cols = _table_columns(con, name)
            pk = entity.get("primaryKey", {}).get("columnNames", [])
            room_cols = {f["columnName"]: f for f in entity["fields"]}
            if set(cols) != set(room_cols):
                problems.append(f"{name}: colunas {sorted(cols)} ≠ Room {sorted(room_cols)}")
                continue
            if "ftsVersion" in entity:
                sql = con.execute("SELECT sql FROM sqlite_master WHERE name=?", (name,)).fetchone()[0]
                expected = entity["createSql"].replace("${TABLE_NAME}", name).replace(" IF NOT EXISTS", "")
                if " ".join(sql.split()) != " ".join(expected.split()):
                    problems.append(f"{name}: SQL FTS difere\n  banco: {sql}\n  Room:  {expected}")
                continue
            for col, f in room_cols.items():
                affinity, notnull, pk_pos = cols[col]
                if affinity != f["affinity"].upper():
                    problems.append(f"{name}.{col}: tipo {affinity} ≠ {f['affinity']}")
                if notnull != f.get("notNull", False):
                    problems.append(f"{name}.{col}: NOT NULL {notnull} ≠ {f.get('notNull', False)}")
                expected_pk = pk.index(col) + 1 if col in pk else 0
                if pk_pos != expected_pk:
                    problems.append(f"{name}.{col}: posição na PK {pk_pos} ≠ {expected_pk}")
            idx = _indices(con, name)
            room_idx = {i["name"]: (i["unique"], i["columnNames"]) for i in entity.get("indices", [])}
            if idx != room_idx:
                problems.append(f"{name}: índices {idx} ≠ Room {room_idx}")
            fks = sorted((r[2], r[3], r[4]) for r in con.execute(f"PRAGMA foreign_key_list(`{name}`)"))
            room_fks = sorted(
                (fk["table"], c, rc)
                for fk in entity.get("foreignKeys", [])
                for c, rc in zip(fk["columns"], fk["referencedColumns"], strict=True)
            )
            if fks != room_fks:
                problems.append(f"{name}: chaves estrangeiras {fks} ≠ Room {room_fks}")
    finally:
        con.close()
    return problems
