"""Limpeza da resposta da LLM: remove raciocínio, extrai o primeiro objeto JSON e valida no schema.

Independe do modelo: funciona com resposta pura, cercada de texto, em bloco ```json``` ou precedida de
`<think>…</think>` (inclusive bloco de raciocínio não fechado, quando a saída é truncada).
"""

import json
import re

from pydantic import BaseModel, ValidationError

DEFAULT_THINKING_TAGS = ("think", "thinking", "reasoning", "thought")


class JsonExtractionError(ValueError):
    pass


def strip_thinking(text: str, tags: tuple[str, ...] = DEFAULT_THINKING_TAGS) -> str:
    for tag in tags:
        t = re.escape(tag)
        text = re.sub(rf"<{t}\b[^>]*>.*?</{t}>", "", text, flags=re.S | re.I)
        # bloco aberto e nunca fechado: descarta até o primeiro "{" depois dele
        m = re.search(rf"<{t}\b[^>]*>", text, flags=re.I)
        if m:
            brace = text.find("{", m.end())
            text = text[: m.start()] + (text[brace:] if brace != -1 else "")
    return text.strip()


def _matching_brace(text: str, start: int) -> int | None:
    """Índice do "}" que fecha o "{" em `start` (respeitando strings), ou None se nunca fecha."""
    depth = 0
    in_str = esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    return None


def _escape_inner_quotes(text: str) -> str:
    """Escapa aspas soltas dentro de strings: `"a ideia de que "nada nos faltará" pode"` (erro comum de
    LLMs pequenas). Uma aspa só fecha a string se o próximo caractere útil for , : } ] ou o fim."""
    out: list[str] = []
    in_str = esc = False
    n = len(text)
    for i, ch in enumerate(text):
        if not in_str:
            in_str = ch == '"'
            out.append(ch)
            continue
        if esc:
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == '"':
            j = i + 1
            while j < n and text[j] in " \t\r\n":
                j += 1
            if j >= n or text[j] in ",:}]":
                in_str = False
            else:
                out.append("\\")
        out.append(ch)
    return "".join(out)


_MORE_KEYS = re.compile(r'\s*,\s*"[^"]{1,40}"\s*:')


def _balance_closers(text: str, autoclose: bool = True) -> str | None:
    """Corrige fechamentos trocados fora de strings: `["a", "b" }` → `["a", "b" ]}` (erro comum de LLMs
    pequenas), fecha o que ficou aberto no fim e descarta fechamentos sem abertura."""
    pairs = {"{": "}", "[": "]"}
    out: list[str] = []
    stack: list[str] = []
    in_str = esc = False
    for i, ch in enumerate(text):
        if in_str:
            out.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in pairs:
            stack.append(pairs[ch])
        elif ch in "}]":
            if ch not in stack:
                continue  # fechamento sem abertura: descarta
            if len(stack) == 1 and _MORE_KEYS.match(text, i + 1):
                continue  # fechou o objeto principal cedo demais: `...]}, "application": ...`
            while stack and stack[-1] != ch:
                out.append(stack.pop())  # fecha o que faltou antes
            stack.pop()
        out.append(ch)
    if stack and not autoclose:
        return None  # ficou algo aberto (resposta truncada)
    out.extend(reversed(stack))
    return "".join(out)


def _repair(candidate: str) -> str:
    """Reparos sintáticos que não mudam conteúdo: delimitadores trocados e vírgula sobrando."""
    escaped = _escape_inner_quotes(candidate)
    return re.sub(r",\s*([}\]])", r"\1", _balance_closers(escaped) or escaped)


def extract_json_object(text: str) -> dict:
    """Primeiro objeto JSON **de nível superior** do texto.

    Nunca desce para um objeto aninhado: se o objeto externo estiver truncado ou inválido, falha
    com uma mensagem útil para a próxima tentativa, em vez de aceitar um pedaço interno.
    """
    first, last = text.find("{"), text.rfind("}")
    if first != -1 and last > first:
        # 1º: o trecho mais longo, reparado (pega objeto fechado cedo demais pela LLM)
        balanced = _balance_closers(_escape_inner_quotes(text[first : last + 1]), autoclose=False)
        if balanced is not None:
            try:
                value = json.loads(re.sub(r",\s*([}\]])", r"\1", balanced))
                if isinstance(value, dict):
                    return value
            except json.JSONDecodeError:
                pass
    pos = 0
    last_error: str | None = None
    while (start := text.find("{", pos)) != -1:
        end = _matching_brace(text, start)
        if end is None:
            raise JsonExtractionError(
                last_error or "JSON incompleto: a resposta terminou antes de fechar o objeto (truncada?)"
            )
        candidate = text[start : end + 1]
        for attempt in (candidate, _repair(candidate)):
            try:
                value = json.loads(attempt)
            except json.JSONDecodeError as exc:
                last_error = f"JSON inválido: {exc.msg} (linha {exc.lineno}, coluna {exc.colno})"
                continue
            if isinstance(value, dict):
                return value
        pos = end + 1  # pula o objeto inteiro (e tudo que está dentro dele)
    raise JsonExtractionError(last_error or "nenhum objeto JSON encontrado na resposta")


def describe_validation_error(exc: ValidationError) -> str:
    """Mensagem curta (pt-BR) para reenviar à LLM na próxima tentativa."""
    parts = []
    for e in exc.errors()[:8]:
        loc = ".".join(str(p) for p in e["loc"]) or "(raiz)"
        parts.append(f"- {loc}: {e['msg']}")
    return "\n".join(parts)


def parse_response[T: BaseModel](text: str, schema: type[T], strip: bool = True) -> T:
    """Texto bruto → instância validada. Levanta JsonExtractionError ou ValidationError."""
    cleaned = strip_thinking(text) if strip else text
    return schema.model_validate(extract_json_object(cleaned))
