"""Fábrica da aplicação FastAPI. `uvicorn app.main:app`.

CORS fica **desligado** de propósito: o único cliente é o app Android (sem navegador), então nenhum
cabeçalho `Access-Control-*` é enviado e navegadores de outras origens não conseguem ler as respostas.
"""

from fastapi import FastAPI

from app.api.v1 import router as v1_router
from app.core.errors import install_error_handlers
from app.core.logging import setup_logging
from app.core.middleware import RequestContextMiddleware


def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(
        title="Maná Diário API",
        version="1.0.0",
        openapi_url="/v1/openapi.json",
        docs_url="/v1/docs",
        redoc_url=None,
    )
    install_error_handlers(app)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(v1_router)
    return app


app = create_app()
