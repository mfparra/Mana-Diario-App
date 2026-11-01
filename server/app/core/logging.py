"""Logs em JSON (uma linha por evento) com request-id e **sem PII**.

Nunca são registrados: corpo de requisição/resposta, cabeçalhos, query string, IP do cliente,
e-mail, nome, texto de perfil ou de anotação, prompts personalizados. Só entram em `extra` as chaves
da lista `ALLOWED_EXTRA` — qualquer outra é descartada, para que um `log.info(..., extra=...)`
descuidado não vaze dados.
"""

import contextvars
import datetime as dt
import json
import logging
import sys
import traceback
from typing import Any

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)

ALLOWED_EXTRA = frozenset(
    {
        "method", "route", "status", "duration_ms", "error_type", "date", "job_id", "kind", "attempt",
        "provider", "model", "prompt_version", "event", "count",
    }
)  # fmt: skip


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, Any] = {
            "ts": dt.datetime.fromtimestamp(record.created, dt.UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        rid = request_id_var.get()
        if rid:
            out["request_id"] = rid
        for key in ALLOWED_EXTRA:
            if key in record.__dict__:
                out[key] = record.__dict__[key]
        if record.exc_info and record.exc_info[0] is not None:
            # só o tipo e o traceback; a mensagem da exceção pode carregar dados do usuário
            out["exc_type"] = record.exc_info[0].__name__
            out["traceback"] = "".join(traceback.format_tb(record.exc_info[2]))
        return json.dumps(out, ensure_ascii=False, default=str)


_configured = False


def setup_logging(level: str = "INFO") -> None:
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.handlers[:] = []
        lg.propagate = True
    # o access log do uvicorn registra o IP do cliente → desligado; o middleware loga sem IP
    access = logging.getLogger("uvicorn.access")
    access.handlers[:] = []
    access.propagate = False
    access.disabled = True
    _configured = True
