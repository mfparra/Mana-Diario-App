"""Modelos SQLAlchemy (PostgreSQL 16). Fonte das migrações Alembic — ver `docs/ARQUITETURA.md` §3.

Regras:
- Toda tabela com dados do usuário referencia `users.id` com `ON DELETE CASCADE`
  (excluir a conta apaga tudo — PRIVACIDADE_LGPD).
- Dados sensíveis (perfil, anotações) só como bytes cifrados (`*_encrypted`/`encrypted_*`).
- Instantes sempre `timestamptz` (UTC); datas do estudo como `date` (dia em America/Sao_Paulo).
"""

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


def _now() -> Any:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


def _user_fk() -> Any:
    return ForeignKey("users.id", ondelete="CASCADE")


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    google_sub: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    name: Mapped[str | None] = mapped_column(String(200))
    photo_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()
    deleted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(_user_fk(), nullable=False, index=True)
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    device_label: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[dt.datetime] = _now()
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class CuratedQuote(Base):
    __tablename__ = "curated_quotes"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str] = mapped_column(String(200), nullable=False)
    source: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(50)), nullable=False, server_default="{}")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sql_text("true"))
    last_used_at: Mapped[dt.date | None] = mapped_column(Date)

    __table_args__ = (
        CheckConstraint("length(trim(author)) > 0", name="author_not_blank"),
        UniqueConstraint("text", "author", name="uq_curated_quotes_text_author"),
    )


class VersePlan(Base):
    __tablename__ = "verse_plan"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    verse_ref: Mapped[str] = mapped_column(String(50), nullable=False)  # canônico USFM, ex.: "JHN 3:16"
    theme: Mapped[str | None] = mapped_column(String(100))
    special_day: Mapped[str | None] = mapped_column(String(50))  # chave do calendário (ex.: "pascoa")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sql_text("true"))

    __table_args__ = (
        UniqueConstraint(
            "verse_ref", "special_day", name="uq_verse_plan_ref_day", postgresql_nulls_not_distinct=True
        ),
        Index("ix_verse_plan_special_day", "special_day"),
    )


class Study(Base):
    __tablename__ = "studies"

    date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="draft")
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    etag: Mapped[str | None] = mapped_column(String(64))
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    verse_ref: Mapped[str] = mapped_column(String(50), nullable=False)
    special_day: Mapped[str | None] = mapped_column(String(50))
    quote_id: Mapped[int | None] = mapped_column(ForeignKey("curated_quotes.id", ondelete="SET NULL"))
    provider: Mapped[str | None] = mapped_column(String(50))
    model: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(50))
    is_fallback: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sql_text("false"))
    generated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status IN ('draft', 'published', 'failed')", name="status_valid"),
        CheckConstraint("status <> 'published' OR payload IS NOT NULL", name="published_has_payload"),
        Index("ix_studies_verse_ref", "verse_ref"),
    )


class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(_user_fk())
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()

    __table_args__ = (
        CheckConstraint("kind IN ('daily', 'personal')", name="kind_valid"),
        CheckConstraint("status IN ('pending', 'running', 'done', 'failed')", name="status_valid"),
        CheckConstraint("(kind = 'personal') = (user_id IS NOT NULL)", name="personal_has_user"),
        Index("ix_generation_jobs_pending", "status", "priority", "created_at"),
    )


class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(_user_fk(), primary_key=True)
    encrypted_payload: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    consent_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consent_version: Mapped[str] = mapped_column(String(20), nullable=False)
    updated_at: Mapped[dt.datetime] = _now()


class PersonalStudy(Base):
    __tablename__ = "personal_studies"

    user_id: Mapped[uuid.UUID] = mapped_column(_user_fk(), primary_key=True)
    date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(50))
    model: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(50))
    generated_at: Mapped[dt.datetime] = _now()


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(_user_fk(), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(String(100), nullable=False)
    purchase_token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    auto_renewing: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sql_text("false"))
    acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sql_text("false"))
    created_at: Mapped[dt.datetime] = _now()
    last_verified_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class Note(Base):
    __tablename__ = "notes"

    user_id: Mapped[uuid.UUID] = mapped_column(_user_fk(), primary_key=True)
    date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    encrypted_body: Mapped[bytes | None] = mapped_column(LargeBinary)  # nulo = tombstone
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    updated_at: Mapped[dt.datetime] = _now()
    deleted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("(deleted_at IS NULL) = (encrypted_body IS NOT NULL)", name="tombstone_consistent"),
        Index("ix_notes_user_updated", "user_id", "updated_at"),
    )
