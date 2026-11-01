import copy
import datetime as dt
import json

import pytest
from sqlalchemy import text

from app.api.v1.studies import get_study_service
from app.services.studies import StudyService, compute_etag

# Exemplo do docs/API.md (Objeto Study)
EXEMPLO = {
    "schema_version": 1,
    "date": "2026-11-01",
    "day_of_year": 305,
    "days_in_year": 365,
    "special_day": None,
    "title": "Supere",
    "verse": {
        "ref": {"book": "PSA", "chapter": 139, "verse_start": 14, "verse_end": 14},
        "display_ref": "Salmos 139.14",
        "text": "<texto da BLIVRE resolvido pelo servidor>",
        "translation": "BLIVRE",
    },
    "body": ["parágrafo 1", "parágrafo 2", "parágrafo 3"],
    "application": "Aplicação prática curta.",
    "prayer": "Oração curta.",
    "quote": {"id": "q_0142", "text": "…", "author": "…", "source": "curated"},
    "complementary_reading": {
        "ref": {"book": "ACT", "chapter": 17, "verse_start": None, "verse_end": None},
        "display_ref": "Atos 17",
        "reason": "Uma linha sobre por que ler.",
    },
    "keywords": ["lealdade", "superação", "amizade"],
    "generated_at": "2026-10-25T03:00:12Z",
}

# "Agora" fixo: 01/11/2026 10:00 em São Paulo (13:00 UTC)
AGORA = dt.datetime(2026, 11, 1, 13, 0, tzinfo=dt.UTC)


def _payload(date: str, **changes) -> dict:
    p = copy.deepcopy(EXEMPLO)
    p["date"] = date
    p.update(changes)
    return p


@pytest.fixture
async def studies_api(api_db, login):
    client, maker = api_db

    async def svc_override():
        async with maker() as s:
            yield StudyService(s, clock=lambda: AGORA)

    client.app.dependency_overrides[get_study_service] = svc_override
    async with maker() as s:
        await s.execute(text("DELETE FROM studies"))
        for d, status in [
            ("2026-10-30", "published"),
            ("2026-10-31", "published"),
            ("2026-11-01", "published"),
            ("2026-11-02", "published"),  # D+1: pode ser visto por quem está a leste
            ("2026-11-03", "published"),  # D+2: ainda não
            ("2026-10-29", "failed"),
        ]:
            payload = _payload(d, title=f"T{d[-2:]}") if d != "2026-11-01" else EXEMPLO
            await s.execute(
                text(
                    "INSERT INTO studies (date, status, payload, verse_ref) "
                    "VALUES (:d, :st, CAST(:p AS jsonb), 'PSA 139:14')"
                ),
                {
                    "d": dt.date.fromisoformat(d),
                    "st": status,
                    "p": json.dumps(payload) if status == "published" else None,
                },
            )
        await s.commit()
    headers, _ = await login()
    return client, headers


async def test_today_igual_ao_exemplo_da_api(studies_api):
    client, h = studies_api
    r = await client.get("/v1/studies/today", headers=h)
    assert r.status_code == 200
    assert r.json() == EXEMPLO
    assert r.headers["etag"] == f'"{compute_etag(EXEMPLO)}"'
    assert r.headers["cache-control"] == "private, max-age=300"


async def test_today_com_fuso_do_aparelho(studies_api):
    client, h = studies_api
    # 13:00 UTC = 01/11 10:00 em SP, mas 02/11 00:00 em Kiritimati (UTC+14) → estudo de 02/11 (D+1)
    r = await client.get("/v1/studies/today", params={"tz": "Pacific/Kiritimati"}, headers=h)
    assert r.json()["date"] == "2026-11-02"
    r = await client.get("/v1/studies/today", params={"tz": "America/Manaus"}, headers=h)
    assert r.json()["date"] == "2026-11-01"
    r = await client.get("/v1/studies/today", params={"tz": "Lua/Base"}, headers=h)
    assert r.status_code == 422


async def test_304_com_if_none_match(studies_api):
    client, h = studies_api
    etag = (await client.get("/v1/studies/2026-11-01", headers=h)).headers["etag"]
    r = await client.get("/v1/studies/2026-11-01", headers={**h, "If-None-Match": etag})
    assert r.status_code == 304
    assert r.content == b"" and r.headers["etag"] == etag
    r = await client.get("/v1/studies/2026-11-01", headers={**h, "If-None-Match": f'W/{etag}, "outro"'})
    assert r.status_code == 304
    r = await client.get("/v1/studies/2026-11-01", headers={**h, "If-None-Match": '"desatualizado"'})
    assert r.status_code == 200


async def test_404_e_422(studies_api):
    client, h = studies_api
    r = await client.get("/v1/studies/2026-10-29", headers=h)  # falhou → não publicado
    assert r.status_code == 404 and r.json()["error"]["code"] == "study_not_available"
    r = await client.get("/v1/studies/2020-01-01", headers=h)
    assert r.status_code == 404
    r = await client.get("/v1/studies/2026-11-02", headers=h)  # D+1 permitido
    assert r.status_code == 200
    r = await client.get("/v1/studies/2026-11-03", headers=h)  # D+2 é futuro
    assert r.status_code == 422
    body = r.json()["error"]
    assert body["code"] == "future_date" and body["details"]["max_date"] == "2026-11-02"
    r = await client.get("/v1/studies/2026-13-01", headers=h)
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


async def test_lista_do_historico(studies_api):
    client, h = studies_api
    r = await client.get("/v1/studies", params={"from": "2026-10-25", "to": "2026-11-30"}, headers=h)
    assert r.status_code == 200
    items = r.json()["items"]
    assert [i["date"] for i in items] == [
        "2026-11-02",
        "2026-11-01",
        "2026-10-31",
        "2026-10-30",
    ]  # sem futuro/falho
    assert items[1] == {"date": "2026-11-01", "title": "Supere", "verse_ref": "PSA 139:14",
                        "keywords": ["lealdade", "superação", "amizade"]}  # fmt: skip


@pytest.mark.parametrize(
    "params",
    [
        {"from": "2026-11-01", "to": "2026-10-01"},
        {"from": "2026-01-01", "to": "2026-12-31"},
        {"from": "2026-11-01"},
    ],
)
async def test_lista_intervalo_invalido(studies_api, params):
    client, h = studies_api
    r = await client.get("/v1/studies", params=params, headers=h)
    assert r.status_code == 422


async def test_exige_login(studies_api):
    client, _ = studies_api
    for path in ("/v1/studies/today", "/v1/studies/2026-11-01", "/v1/studies?from=2026-11-01&to=2026-11-01"):
        assert (await client.get(path)).status_code == 401


def test_etag_estavel_e_sensivel_ao_conteudo():
    assert compute_etag(EXEMPLO) == compute_etag(json.loads(json.dumps(EXEMPLO)))
    assert compute_etag(EXEMPLO) != compute_etag(_payload("2026-11-01", title="Outro"))
