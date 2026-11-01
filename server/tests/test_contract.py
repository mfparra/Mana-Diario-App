"""Contrato: docs/openapi.json atualizado e toda rota implementada documentada em docs/API.md."""

import json
import re

from app.cli import DOCS, openapi_json

API_MD = (DOCS / "API.md").read_text()


def test_openapi_exportado_esta_atualizado():
    salvo = (DOCS / "openapi.json").read_text()
    assert json.loads(salvo) == json.loads(openapi_json()), (
        "docs/openapi.json desatualizado: rode `uv run python -m app.cli export-openapi`"
    )


def _normaliza(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "{}", path.removeprefix("/v1"))


def test_toda_rota_implementada_esta_no_api_md():
    spec = json.loads(openapi_json())
    documentadas = {
        (m.upper(), _normaliza(p.split("?")[0]))
        for m, p in re.findall(r"\b(GET|POST|PUT|PATCH|DELETE) (/[\w/{}.-]+(?:\?[^\s`]*)?)", API_MD)
    }
    faltando = []
    for path, ops in spec["paths"].items():
        for method in ops:
            if (method.upper(), _normaliza(path)) not in documentadas:
                faltando.append(f"{method.upper()} {path}")
    assert faltando == [], f"rotas sem documentação em docs/API.md: {faltando}"


PUBLICAS = {"/v1/health", "/v1/auth/google", "/v1/auth/refresh", "/v1/auth/logout"}


async def test_so_health_e_auth_sao_publicas():
    """Toda rota do contrato, exceto /health e /auth/*, responde 401 sem token (docs/API.md)."""
    import httpx

    from app.core.config import Settings, get_settings
    from app.db.session import get_session
    from app.main import create_app

    async def sem_banco():
        yield None

    app = create_app()
    app.dependency_overrides[get_session] = sem_banco
    app.dependency_overrides[get_settings] = lambda: Settings(llm_provider="fake", jwt_secret="s" * 40)
    spec = app.openapi()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        for path, ops in spec["paths"].items():
            if path in PUBLICAS:
                continue
            url = re.sub(r"\{[^}]+\}", "2026-11-01", path)
            for method in ops:
                r = await c.request(method.upper(), url, json={})
                # admin usa X-Admin-Token (403; 503 se ADMIN_TOKEN não estiver configurado)
                esperado = {403, 503} if path.startswith("/v1/admin/") else {401}
                assert r.status_code in esperado, f"{method.upper()} {path} → {r.status_code}"
    assert set(spec["paths"]) >= PUBLICAS
