"""Migrações Alembic num PostgreSQL real. Requer TEST_DATABASE_URL (ver scripts/test-db.sh)."""

import datetime as dt
import os
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.db.models import Base

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL não definida (scripts/test-db.sh up)")

SERVER = Path(__file__).resolve().parents[1]
TABELAS = {
    "users",
    "refresh_tokens",
    "studies",
    "generation_jobs",
    "verse_plan",
    "curated_quotes",
    "user_profiles",
    "personal_studies",
    "subscriptions",
    "notes",
}


def _alembic() -> Config:
    cfg = Config(str(SERVER / "alembic.ini"))
    cfg.set_main_option("script_location", str(SERVER / "migrations"))
    cfg.set_main_option("sqlalchemy.url", URL)
    cfg.attributes["skip_logging"] = True
    return cfg


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(URL)
    with eng.begin() as conn:  # começa de um banco limpo
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    yield eng
    eng.dispose()


def _tabelas(engine) -> set[str]:
    return set(inspect(engine).get_table_names()) - {"alembic_version"}


def test_ida_e_volta(engine):
    cfg = _alembic()
    command.upgrade(cfg, "head")
    assert _tabelas(engine) == TABELAS
    command.downgrade(cfg, "base")
    assert _tabelas(engine) == set()
    command.upgrade(cfg, "head")
    assert _tabelas(engine) == TABELAS


def test_modelos_e_migracoes_em_sincronia(engine):
    command.upgrade(_alembic(), "head")
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    assert diff == [], f"Modelos diferem das migrações — gere uma nova revisão: {diff}"


def test_excluir_usuario_apaga_dados_relacionados(engine):
    command.upgrade(_alembic(), "head")
    uid = uuid.uuid4()
    hoje = dt.date(2026, 11, 1)
    agora = dt.datetime.now(dt.UTC)
    with engine.begin() as c:
        c.execute(
            text("INSERT INTO users (id, google_sub, email) VALUES (:id, :sub, 'a@b.c')"),
            {"id": uid, "sub": f"sub-{uid}"},
        )
        c.execute(
            text("INSERT INTO notes (user_id, date, encrypted_body) VALUES (:u, :d, '\\x01')"),
            {"u": uid, "d": hoje},
        )
        c.execute(
            text(
                "INSERT INTO refresh_tokens (id, user_id, family_id, token_hash, expires_at) "
                "VALUES (:i, :u, :f, :h, :e)"
            ),
            {"i": uuid.uuid4(), "u": uid, "f": uuid.uuid4(), "h": f"h-{uid}", "e": agora},
        )
        c.execute(
            text(
                "INSERT INTO user_profiles (user_id, encrypted_payload, consent_at, consent_version) "
                "VALUES (:u, '\\x02', :a, 'v1')"
            ),
            {"u": uid, "a": agora},
        )
        c.execute(
            text("INSERT INTO personal_studies (user_id, date, payload) VALUES (:u, :d, '{}')"),
            {"u": uid, "d": hoje},
        )
        c.execute(
            text(
                "INSERT INTO subscriptions (user_id, product_id, purchase_token_hash, status) "
                "VALUES (:u, 'mana_premium', :h, 'active')"
            ),
            {"u": uid, "h": f"p-{uid}"},
        )
        c.execute(
            text("INSERT INTO generation_jobs (kind, date, user_id) VALUES ('personal', :d, :u)"),
            {"u": uid, "d": hoje},
        )
        c.execute(text("DELETE FROM users WHERE id = :u"), {"u": uid})
        for tabela in (
            "notes",
            "refresh_tokens",
            "user_profiles",
            "personal_studies",
            "subscriptions",
            "generation_jobs",
        ):
            n = c.execute(text(f"SELECT count(*) FROM {tabela} WHERE user_id = :u"), {"u": uid}).scalar()
            assert n == 0, tabela


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO studies (date, status, verse_ref) VALUES ('2026-11-02', 'published', 'JHN 3:16')",
        "INSERT INTO studies (date, status, verse_ref) VALUES ('2026-11-03', 'qualquer', 'JHN 3:16')",
        "INSERT INTO curated_quotes (text, author) VALUES ('frase', '  ')",
        "INSERT INTO generation_jobs (kind, date) VALUES ('personal', '2026-11-02')",
    ],
)
def test_restricoes_do_banco(engine, sql):
    command.upgrade(_alembic(), "head")
    with pytest.raises(IntegrityError), engine.begin() as c:
        c.execute(text(sql))
