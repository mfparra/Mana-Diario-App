"""Middleware ASGI: request-id, log de acesso sem PII e 500 no formato padrão de erro."""

import json
import logging
import re
import time
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import error_body
from app.core.logging import request_id_var

log = logging.getLogger("app.access")
_VALID_RID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
HEADER = "x-request-id"


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = dict(scope.get("headers") or []).get(HEADER.encode(), b"").decode("latin-1")
        rid = incoming if _VALID_RID.match(incoming) else uuid.uuid4().hex
        token = request_id_var.set(rid)
        start = time.perf_counter()
        status = 500
        started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal status, started
            if message["type"] == "http.response.start":
                status, started = message["status"], True
                message["headers"] = [*message.get("headers", []), (HEADER.encode(), rid.encode())]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            # Fica aqui (e não no handler do Starlette) para o 500 ter request-id no log e no cabeçalho.
            log.exception("erro não tratado", extra={"error_type": type(exc).__name__})
            if started:
                raise
            body = json.dumps(
                error_body("internal_error", "Erro interno. Tente novamente mais tarde."), ensure_ascii=False
            ).encode()
            await send_wrapper(
                {
                    "type": "http.response.start",
                    "status": 500,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                    ],
                }
            )
            await send_wrapper({"type": "http.response.body", "body": body})
        finally:
            route = scope.get("route")
            # modelo da rota (/v1/notes/{date}) quando houver; nunca a query string
            # caminho bruto de rota inexistente pode conter qualquer coisa → não registrar
            path = getattr(route, "path", None) or "<sem rota>"
            if path != "/v1/health":
                log.info(
                    "request",
                    extra={
                        "method": scope.get("method"),
                        "route": path,
                        "status": status,
                        "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                    },
                )
            request_id_var.reset(token)
