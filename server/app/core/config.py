"""Configuração via variáveis de ambiente (`infra/.env`). Nenhum segredo tem valor padrão real."""

import json
from functools import lru_cache
from typing import Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=False)

    app_env: Literal["development", "test", "staging", "production"] = "development"
    app_timezone: str = "America/Sao_Paulo"

    database_url: str | None = None
    blivre_sqlite_path: str = "/data/blivre.sqlite"
    crossrefs_sqlite_path: str = "/data/crossrefs.sqlite"

    admin_token: str | None = None
    jwt_secret: str | None = None
    field_encryption_key: str | None = None
    google_web_client_id: str | None = None

    # LLM — ver docs/LLM_SERVER.md §4
    llm_provider: Literal["openai_compatible", "fake"] = "openai_compatible"
    llm_base_url: str = "http://llm:8081/v1"
    llm_api_key: str | None = None
    llm_model: str = ""  # sem padrão: nome de modelo só no .env (regra: nada de modelo fora de app/llm)
    llm_json_mode: Literal["none", "json_object", "json_schema"] = "none"
    llm_extra_body: dict[str, Any] = Field(default_factory=dict)
    llm_strip_thinking: bool = True
    llm_temperature: float = 0.7
    llm_max_tokens: int = 2000
    llm_context_tokens: int = 4096
    llm_timeout_s: float = 300
    llm_max_concurrency: int = 1
    llm_max_retries: int = 3
    llm_sends_personal_data: bool = True
    llm_health_timeout_s: float = 3

    @field_validator("llm_extra_body", mode="before")
    @classmethod
    def _parse_extra_body(cls, v: Any) -> Any:
        if isinstance(v, str):
            return json.loads(v) if v.strip() else {}
        return v

    @field_validator(
        "llm_api_key",
        "admin_token",
        "jwt_secret",
        "field_encryption_key",
        "database_url",
        "google_web_client_id",
        mode="before",
    )
    @classmethod
    def _empty_is_none(cls, v: Any) -> Any:
        return None if v == "" else v


@lru_cache
def get_settings() -> Settings:
    return Settings()
