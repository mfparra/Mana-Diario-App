"""Fábrica da aplicação FastAPI. `uvicorn app.main:app`."""

from fastapi import FastAPI

from app.api.v1 import router as v1_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Maná Diário API",
        version="1.0.0",
        openapi_url="/v1/openapi.json",
        docs_url="/v1/docs",
        redoc_url=None,
    )
    app.include_router(v1_router)
    return app


app = create_app()
