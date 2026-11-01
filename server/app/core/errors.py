"""Formato único de erro da API (docs/API.md):

    { "error": { "code": "study_not_available", "message": "Texto em pt-BR", "details": {} } }

Regra de privacidade: `details` nunca ecoa valores enviados pelo cliente (podem conter dados pessoais),
só a localização e o tipo do problema.
"""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("app.errors")


class ApiError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ):
        super().__init__(code)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        self.headers = headers


_HTTP_DEFAULTS: dict[int, tuple[str, str]] = {
    400: ("bad_request", "Requisição inválida."),
    401: ("unauthorized", "Autenticação necessária."),
    403: ("forbidden", "Acesso negado."),
    404: ("not_found", "Recurso não encontrado."),
    405: ("method_not_allowed", "Método não permitido."),
    409: ("conflict", "Conflito com o estado atual do recurso."),
    413: ("payload_too_large", "Conteúdo grande demais."),
    415: ("unsupported_media_type", "Tipo de conteúdo não suportado."),
    422: ("validation_error", "Dados inválidos."),
    429: ("rate_limited", "Muitas requisições. Tente novamente em instantes."),
    500: ("internal_error", "Erro interno. Tente novamente mais tarde."),
    503: ("unavailable", "Serviço temporariamente indisponível."),
}


def error_body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def _response(status: int, code: str, message: str, details=None, headers=None) -> JSONResponse:
    return JSONResponse(error_body(code, message, details), status_code=status, headers=headers)


async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
    return _response(exc.status_code, exc.code, exc.message, exc.details, exc.headers)


async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code, message = _HTTP_DEFAULTS.get(exc.status_code, ("error", "Erro."))
    return _response(exc.status_code, code, message, headers=getattr(exc, "headers", None))


async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    fields = [
        {"loc": [str(p) for p in e.get("loc", ())], "type": e.get("type", "invalid")} for e in exc.errors()
    ]
    return _response(422, "validation_error", "Dados inválidos.", {"fields": fields})


async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
    log.exception("erro não tratado", extra={"error_type": type(exc).__name__})
    code, message = _HTTP_DEFAULTS[500]
    return _response(500, code, message)


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(Exception, _unhandled)
