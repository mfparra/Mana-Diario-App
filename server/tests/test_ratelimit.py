import pytest

from app.core.ratelimit import AUTH, NOTES, STUDIES, RateLimiter, Rule


class Relogio:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_janela_fixa():
    rel = Relogio()
    lim = RateLimiter(clock=rel)
    regra = Rule("x", 3, 60)
    assert [lim.hit(regra, "a") for _ in range(3)] == [None, None, None]
    rel.t += 10
    assert lim.hit(regra, "a") == pytest.approx(50)
    assert lim.hit(regra, "b") is None  # chaves independentes
    rel.t += 50
    assert lim.hit(regra, "a") is None  # janela nova


def test_limpeza_de_chaves_antigas():
    rel = Relogio()
    lim = RateLimiter(clock=rel, max_keys=10)
    for i in range(10):
        lim.hit(AUTH, f"ip{i}")
    rel.t += 4000
    lim.hit(AUTH, "novo")  # passa do limite de chaves → remove as expiradas
    assert len(lim._buckets) == 1


def test_limites_do_contrato():
    assert (AUTH.limit, AUTH.window_s) == (10, 60)
    assert (STUDIES.limit, STUDIES.window_s) == (60, 60)
    assert (NOTES.limit, NOTES.window_s) == (120, 60)


async def test_auth_limitado_por_ip(api_db, make_google_token):
    client, _ = api_db
    codigos = []
    for _ in range(11):
        r = await client.post("/v1/auth/refresh", json={"refresh_token": "x" * 43})
        codigos.append(r.status_code)
    assert codigos[:10] == [401] * 10
    assert codigos[10] == 429
    assert r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1
    assert r.json()["error"]["details"]["retry_after_seconds"] == int(r.headers["retry-after"])


async def test_notas_limitadas_por_usuario(api_db, login):
    client, _ = api_db
    h1, _ = await login()
    h2, _ = await login()
    client.app.state.limiter = RateLimiter()
    for _ in range(NOTES.limit):
        assert (await client.get("/v1/notes", headers=h1)).status_code == 200
    assert (await client.get("/v1/notes", headers=h1)).status_code == 429
    assert (await client.get("/v1/notes", headers=h2)).status_code == 200  # outro usuário não é afetado


async def test_sem_login_nao_consome_limite_de_usuario(api_db):
    client, _ = api_db
    for _ in range(3):
        assert (await client.get("/v1/notes")).status_code == 401
