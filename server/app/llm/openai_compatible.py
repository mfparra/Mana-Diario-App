"""Cliente para qualquer API compatível com OpenAI (`/v1/chat/completions`):
llama.cpp (llm-server), Ollama, vLLM, LM Studio, OpenRouter, OpenAI...

Tudo que varia entre modelos vem do `.env` (LLM_*): modo de JSON, corpo extra, remoção de raciocínio.
"""

import asyncio
import copy
from typing import Any

import httpx
from pydantic import BaseModel

from app.core.config import Settings
from app.llm.base import LlmContextOverflow, LlmHealth, LlmResult, LlmUnavailable, LlmUsage
from app.llm.generation import CompletionOut, Validator, generate_with_retries, schema_hint

# Um semáforo por processo: o llm-server atende 1 requisição por vez e é compartilhado.
_semaphores: dict[int, asyncio.Semaphore] = {}


def _semaphore(n: int) -> asyncio.Semaphore:
    return _semaphores.setdefault(n, asyncio.Semaphore(n))


def estimate_tokens(text: str) -> int:
    """Estimativa conservadora (pt-BR ≈ 3,2 caracteres/token nos tokenizadores comuns)."""
    return int(len(text) / 3.2) + 8


def _deep_merge(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in extra.items():
        out[k] = _deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


class OpenAICompatibleClient:
    provider = "openai_compatible"

    def __init__(self, settings: Settings, http: httpx.AsyncClient | None = None):
        if not settings.llm_model:
            raise ValueError("LLM_MODEL não configurado")
        self.s = settings
        self.model = settings.llm_model
        self._http = http
        self._base = settings.llm_base_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.s.llm_api_key}"} if self.s.llm_api_key else {}

    def build_body(
        self, messages: list[dict[str, str]], schema: type[BaseModel], temperature: float, max_tokens: int
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if self.s.llm_json_mode == "json_object":
            body["response_format"] = {"type": "json_object"}
        elif self.s.llm_json_mode == "json_schema":
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "schema": schema.model_json_schema(),
                    "strict": True,
                },
            }
        return _deep_merge(body, self.s.llm_extra_body)

    async def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base}/chat/completions"
        timeout = httpx.Timeout(self.s.llm_timeout_s, connect=10)
        try:
            if self._http is None:
                async with httpx.AsyncClient(timeout=timeout) as c:
                    resp = await c.post(url, json=body, headers=self._headers())
            else:
                resp = await self._http.post(url, json=body, headers=self._headers(), timeout=timeout)
        except httpx.TimeoutException as exc:
            raise LlmUnavailable(f"timeout após {self.s.llm_timeout_s:.0f}s") from exc
        except httpx.HTTPError as exc:
            raise LlmUnavailable(f"falha de conexão: {type(exc).__name__}") from exc
        if resp.status_code != 200:
            raise LlmUnavailable(f"HTTP {resp.status_code} do provedor")
        try:
            return resp.json()
        except ValueError as exc:
            raise LlmUnavailable("resposta do provedor não é JSON") from exc

    async def generate_json[T: BaseModel](
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        temperature: float | None = None,
        max_tokens: int | None = None,
        validate: Validator | None = None,
    ) -> LlmResult[T]:
        temperature = self.s.llm_temperature if temperature is None else temperature
        max_tokens = max_tokens or self.s.llm_max_tokens
        if self.s.llm_json_mode != "json_schema":
            system = system + schema_hint(schema)
        # orçamento: falha cedo em vez de deixar o provedor truncar ou recusar
        prompt_tokens = estimate_tokens(system) + estimate_tokens(user)
        if prompt_tokens + max_tokens > self.s.llm_context_tokens:
            raise LlmContextOverflow(
                f"prompt (~{prompt_tokens} tokens) + saída ({max_tokens}) excede o contexto "
                f"({self.s.llm_context_tokens})"
            )

        async def complete(messages: list[dict[str, str]]) -> CompletionOut:
            body = self.build_body(messages, schema, temperature, max_tokens)
            async with _semaphore(self.s.llm_max_concurrency):
                data = await self._post(body)
            try:
                choice = data["choices"][0]
                content = choice["message"].get("content") or ""
            except (KeyError, IndexError, TypeError) as exc:
                raise LlmUnavailable("resposta sem choices[0].message") from exc
            u = data.get("usage") or {}
            return CompletionOut(
                content,
                LlmUsage(u.get("prompt_tokens", 0), u.get("completion_tokens", 0)),
                truncated=choice.get("finish_reason") == "length",
            )

        return await generate_with_retries(
            complete,
            system=system,
            user=user,
            schema=schema,
            max_attempts=self.s.llm_max_retries,
            strip_thinking=self.s.llm_strip_thinking,
            provider=self.provider,
            model=self.model,
            validate=validate,
        )

    async def health(self) -> LlmHealth:
        try:
            if self._http is None:
                async with httpx.AsyncClient(timeout=self.s.llm_health_timeout_s) as c:
                    resp = await c.get(f"{self._base}/models", headers=self._headers())
            else:
                resp = await self._http.get(
                    f"{self._base}/models", headers=self._headers(), timeout=self.s.llm_health_timeout_s
                )
        except httpx.HTTPError as exc:
            return LlmHealth(False, self.provider, self.model, type(exc).__name__)
        if resp.status_code != 200:
            return LlmHealth(False, self.provider, self.model, f"HTTP {resp.status_code}")
        try:
            ids = [m.get("id") for m in resp.json().get("data", [])]
        except (ValueError, AttributeError):
            ids = []
        if ids and self.model not in ids:
            return LlmHealth(False, self.provider, self.model, f"modelo não servido; disponíveis: {ids}")
        return LlmHealth(True, self.provider, self.model)
