"""Laço comum de geração com validação e novas tentativas — usado por todos os provedores."""

import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from app.llm.base import LlmInvalidOutput, LlmResult, LlmUsage
from app.llm.parsing import JsonExtractionError, describe_validation_error, parse_response


@dataclass
class CompletionOut:
    text: str
    usage: LlmUsage
    truncated: bool = False  # o provedor parou por limite de tokens (finish_reason == "length")


Completion = Callable[[list[dict[str, str]]], Awaitable[CompletionOut]]


def _inline_refs(node: Any, defs: dict[str, Any]) -> Any:
    """Expande `$ref`/`$defs` (modelos pequenos às vezes copiam o `$defs` na resposta)."""
    if isinstance(node, dict):
        if "$ref" in node:
            return _inline_refs(defs[node["$ref"].rsplit("/", 1)[-1]], defs)
        return {k: _inline_refs(v, defs) for k, v in node.items() if k not in ("$defs", "title")}
    if isinstance(node, list):
        return [_inline_refs(v, defs) for v in node]
    return node


def schema_hint(schema: type[BaseModel]) -> str:
    """Instrução de formato anexada ao sistema quando o provedor não força JSON por schema."""
    raw = schema.model_json_schema()
    compact = json.dumps(_inline_refs(raw, raw.get("$defs", {})), ensure_ascii=False, separators=(",", ":"))
    return (
        "\n\nFormato da resposta: SOMENTE um objeto JSON válido, sem texto antes ou depois e sem markdown. "
        "O JSON Schema abaixo descreve os campos; responda com os VALORES preenchidos, nunca com o schema:\n"
        f"{compact}"
    )


def retry_message(error: str) -> str:
    return (
        "A resposta anterior não foi aceita pelos seguintes motivos:\n"
        f"{error}\n"
        "Corrija e responda novamente SOMENTE com o objeto JSON completo."
    )


async def generate_with_retries[T: BaseModel](
    complete: Completion,
    *,
    system: str,
    user: str,
    schema: type[T],
    max_attempts: int,
    strip_thinking: bool,
    provider: str,
    model: str,
) -> LlmResult[T]:
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    errors: list[str] = []
    usage = LlmUsage()
    raw = ""
    start = time.monotonic()
    for attempt in range(1, max_attempts + 1):
        out = await complete(messages)
        raw = out.text
        usage.prompt_tokens += out.usage.prompt_tokens
        usage.completion_tokens += out.usage.completion_tokens
        try:
            data = parse_response(raw, schema, strip=strip_thinking)
        except ValidationError as exc:
            err = describe_validation_error(exc)
        except JsonExtractionError as exc:
            err = f"- {exc}"
        else:
            return LlmResult(data, provider, model, attempt, time.monotonic() - start, usage, errors)
        if out.truncated:
            err += "\n- a resposta foi cortada pelo limite de tokens: seja mais conciso e feche o JSON"
        errors.append(err)
        # Não reenvia a resposta inválida (estouraria contextos pequenos): só o pedido + o erro.
        messages = [messages[0], {"role": "user", "content": f"{user}\n\n{retry_message(err)}"}]
    raise LlmInvalidOutput(
        f"resposta inválida após {max_attempts} tentativa(s)", last_error=errors[-1], raw=raw
    )
