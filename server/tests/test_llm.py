import asyncio
import json
import re
from pathlib import Path

import httpx
import pytest
from pydantic import BaseModel

from app.core.config import Settings
from app.llm import LlmContextOverflow, LlmInvalidOutput, LlmUnavailable, get_llm_client
from app.llm.fake import FakeLlmClient
from app.llm.openai_compatible import OpenAICompatibleClient
from app.llm.parsing import JsonExtractionError, extract_json_object, strip_thinking


class Saida(BaseModel):
    title: str
    n: int


OK = '{"title": "Paz", "n": 1}'


# --- limpeza e extração ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "texto",
    [
        OK,
        f"<think>vou pensar {{ não é json }}</think>\n{OK}",
        f"<thinking>raciocínio</thinking>{OK}",
        f"<think>raciocínio que nunca fecha... {OK}",  # saída truncada no meio do raciocínio
        f"Claro! Aqui está o JSON pedido:\n```json\n{OK}\n```\nEspero ter ajudado.",
        f'Texto com {{chaves soltas}} antes. {OK} e depois {{"outro": 2}}',
        '{"title": "Use \\"aspas\\" e {chaves} dentro", "n": 1}',
    ],
)
def test_extrai_json(texto):
    obj = extract_json_object(strip_thinking(texto))
    assert set(obj) == {"title", "n"}


def test_sem_json_levanta():
    with pytest.raises(JsonExtractionError):
        extract_json_object("sem objeto aqui [1, 2]")
    with pytest.raises(JsonExtractionError):
        extract_json_object('{"title": "truncado", "n":')


# --- laço de tentativas (via FakeLlmClient, mesmo laço dos clientes reais) ---------------------


async def test_sucesso_na_primeira():
    fake = FakeLlmClient([f"<think>x</think>{OK}"])
    r = await fake.generate_json(system="s", user="u", schema=Saida)
    assert (r.data.title, r.attempts, r.errors) == ("Paz", 1, [])


async def test_json_invalido_reenvia_com_erro_e_corrige():
    fake = FakeLlmClient(['{"title": "Paz"}', "lixo sem json", OK])
    r = await fake.generate_json(system="s", user="pedido original", schema=Saida)
    assert r.attempts == 3
    assert len(r.errors) == 2 and "n" in r.errors[0]
    # a 2ª chamada leva o pedido original + o erro, sem a resposta inválida
    segunda = fake.calls[1]
    assert [m["role"] for m in segunda] == ["system", "user"]
    assert segunda[1]["content"].startswith("pedido original") and "não foi aceita" in segunda[1]["content"]


async def test_falha_apos_tentativas():
    fake = FakeLlmClient(["{}", "{}", "{}"], max_attempts=3)
    with pytest.raises(LlmInvalidOutput) as exc:
        await fake.generate_json(system="s", user="u", schema=Saida)
    assert "title" in exc.value.last_error
    assert len(fake.calls) == 3


async def test_erro_do_provedor_nao_e_repetido_pelo_laco():
    fake = FakeLlmClient([LlmUnavailable("fora do ar"), OK])
    with pytest.raises(LlmUnavailable):
        await fake.generate_json(system="s", user="u", schema=Saida)


# --- cliente OpenAI-compatível com transporte simulado ------------------------------------------


def _settings(**kw) -> Settings:
    base = dict(llm_base_url="http://llm:8081/v1", llm_model="modelo-x", llm_timeout_s=5, llm_max_retries=3)
    return Settings(**{**base, **kw})


def _chat(content: str, usage=(10, 5)) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": usage[0], "completion_tokens": usage[1]},
        },
    )


def _client(handler, **kw) -> OpenAICompatibleClient:
    return OpenAICompatibleClient(
        _settings(**kw), http=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )


async def test_modo_none_sem_response_format_e_com_dica_de_schema():
    bodies = []

    def h(req):
        bodies.append(json.loads(req.content))
        return _chat(f"<think>pensando</think>{OK}")

    c = _client(h, llm_json_mode="none", llm_extra_body={"chat_template_kwargs": {"enable_thinking": False}})
    r = await c.generate_json(system="sistema", user="usuário", schema=Saida)
    assert r.data.n == 1 and r.model == "modelo-x" and r.provider == "openai_compatible"
    assert r.usage.prompt_tokens == 10
    b = bodies[0]
    assert "response_format" not in b
    assert b["chat_template_kwargs"] == {"enable_thinking": False}
    assert b["model"] == "modelo-x" and b["stream"] is False
    assert "JSON Schema" in b["messages"][0]["content"]


async def test_modo_json_schema():
    bodies = []

    def h(req):
        bodies.append(json.loads(req.content))
        return _chat(OK)

    await _client(h, llm_json_mode="json_schema").generate_json(system="s", user="u", schema=Saida)
    rf = bodies[0]["response_format"]
    assert rf["type"] == "json_schema" and rf["json_schema"]["schema"]["title"] == "Saida"
    assert "JSON Schema" not in bodies[0]["messages"][0]["content"]  # o provedor já força o schema


async def test_modo_json_object_e_extra_body_profundo():
    bodies = []

    def h(req):
        bodies.append(json.loads(req.content))
        return _chat(OK)

    c = _client(
        h, llm_json_mode="json_object", llm_extra_body={"response_format": {"extra": 1}, "top_p": 0.9}
    )
    await c.generate_json(system="s", user="u", schema=Saida, temperature=0.2, max_tokens=300)
    b = bodies[0]
    assert b["response_format"] == {"type": "json_object", "extra": 1}
    assert (b["top_p"], b["temperature"], b["max_tokens"]) == (0.9, 0.2, 300)


async def test_timeout():
    def h(req):
        raise httpx.ReadTimeout("lento")

    with pytest.raises(LlmUnavailable, match="timeout"):
        await _client(h).generate_json(system="s", user="u", schema=Saida)


@pytest.mark.parametrize("status", [400, 500, 503])
async def test_http_erro(status):
    with pytest.raises(LlmUnavailable, match=str(status)):
        await _client(lambda req: httpx.Response(status)).generate_json(system="s", user="u", schema=Saida)


async def test_json_invalido_ate_esgotar():
    calls = []

    def h(req):
        calls.append(1)
        return _chat("não é json")

    with pytest.raises(LlmInvalidOutput):
        await _client(h, llm_max_retries=2).generate_json(system="s", user="u", schema=Saida)
    assert len(calls) == 2


async def test_orcamento_de_contexto_falha_antes_de_chamar():
    def h(req):
        raise AssertionError("não deveria chamar o provedor")

    c = _client(h, llm_context_tokens=1000, llm_max_tokens=800)
    with pytest.raises(LlmContextOverflow):
        await c.generate_json(system="s" * 2000, user="u", schema=Saida)


async def test_semaforo_limita_concorrencia():
    ativos = maximo = 0

    async def h(req):
        nonlocal ativos, maximo
        ativos += 1
        maximo = max(maximo, ativos)
        await asyncio.sleep(0.02)
        ativos -= 1
        return _chat(OK)

    c = _client(h, llm_max_concurrency=1)
    await asyncio.gather(*(c.generate_json(system="s", user="u", schema=Saida) for _ in range(4)))
    assert maximo == 1


async def test_health_confere_modelo_servido():
    def h(req):
        assert req.url.path == "/v1/models"
        return httpx.Response(200, json={"data": [{"id": "outro"}]})

    hl = await _client(h).health()
    assert not hl.ok and "outro" in hl.detail
    ok = await _client(lambda r: httpx.Response(200, json={"data": [{"id": "modelo-x"}]})).health()
    assert ok.ok


def test_fabrica_por_provedor():
    assert get_llm_client(_settings()).provider == "openai_compatible"
    assert get_llm_client(_settings(llm_provider="fake")).provider == "fake"
    with pytest.raises(ValueError):
        OpenAICompatibleClient(_settings(llm_model=""))


def test_nenhum_nome_de_modelo_fora_de_app_llm():
    """Regra do AGENTS.md: particularidades de modelo só no adaptador."""
    raiz = Path(__file__).resolve().parents[1]
    proibido = re.compile(r"gemma|qwen|llama|mistral|deepseek|phi-?\d|gpt-\d|claude|<think", re.I)
    achados = []
    for pasta in ("app", "worker"):
        for arq in (raiz / pasta).rglob("*.py"):
            if "llm" in arq.relative_to(raiz / pasta).parts[:1]:
                continue
            for n, linha in enumerate(arq.read_text().splitlines(), 1):
                if proibido.search(linha):
                    achados.append(f"{arq.relative_to(raiz)}:{n}: {linha.strip()}")
    assert achados == []


def test_nao_aceita_objeto_interno_de_externo_truncado():
    """Caso real (Gemma): o objeto externo cortado não pode virar o interno 'complementary_reading'."""
    truncado = (
        '{"title": "PAZ", "complementary_reading": {"candidate_index": 1, "reason": "ok"}, "body": ["...'
    )
    with pytest.raises(JsonExtractionError, match="incompleto"):
        extract_json_object(truncado)


def test_nao_aceita_objeto_interno_de_externo_invalido():
    invalido = '{"title": PAZ, "interno": {"a": 1}}'
    with pytest.raises(JsonExtractionError, match="JSON inválido"):
        extract_json_object(invalido)


def test_repara_virgula_sobrando():
    assert extract_json_object('{"title": "Paz", "n": 1, "lista": [1, 2,],}') == {
        "title": "Paz",
        "n": 1,
        "lista": [1, 2],
    }


async def test_resposta_cortada_por_limite_avisa_na_proxima_tentativa():
    calls = []

    def h(req):
        calls.append(json.loads(req.content))
        if len(calls) == 1:
            return httpx.Response(
                200, json={"choices": [{"message": {"content": '{"title": "Pa'}, "finish_reason": "length"}]}
            )
        return _chat(OK)

    r = await _client(h).generate_json(system="s", user="u", schema=Saida)
    assert r.attempts == 2
    assert "limite de tokens" in r.errors[0]
    assert "limite de tokens" in calls[1]["messages"][1]["content"]


def test_repara_lista_fechada_com_chave_caso_real_gemma():
    """Saída real do Gemma 4 (2026-10-31): `"keywords": [ ..., "paz" }` + `}` sobrando, dentro de ```json."""
    texto = """```json
{
  "title": "PAZ",
  "complementary_reading": {"candidate_index": 1, "reason": "Isaías 40.11 reforça a imagem do pastor."},
  "keywords": [
    "pastoreio",
    "paz"
  }
}
```"""
    obj = extract_json_object(texto)
    assert obj["keywords"] == ["pastoreio", "paz"]
    assert obj["complementary_reading"]["candidate_index"] == 1
    assert obj["title"] == "PAZ"


def test_reparo_nao_mexe_em_delimitadores_dentro_de_strings():
    assert extract_json_object('{"title": "a } ] [ {", "n": [1, 2 }') == {"title": "a } ] [ {", "n": [1, 2]}


def test_dica_de_schema_sem_defs():
    from app.domain.study import StudyLlmOutput
    from app.llm.generation import schema_hint

    hint = schema_hint(StudyLlmOutput)
    assert "$defs" not in hint and "$ref" not in hint
    assert "candidate_index" in hint  # o submodelo foi expandido no lugar
    assert "VALORES" in hint


async def test_regras_de_conteudo_entram_no_laco_de_tentativas():
    fake = FakeLlmClient(['{"title": "Paz", "n": 99}', '{"title": "Paz", "n": 2}'])

    def regras(s: Saida) -> list[str]:
        return ["n deve ser menor que 10"] if s.n >= 10 else []

    r = await fake.generate_json(system="s", user="u", schema=Saida, validate=regras)
    assert (r.data.n, r.attempts) == (2, 2)
    assert "n deve ser menor que 10" in fake.calls[1][1]["content"]


def test_repara_objeto_principal_fechado_cedo_caso_real_gemma():
    """Saída real do Gemma 4 (2026-11-01): fechou o objeto depois do body: `...]}, "application": [...]`."""
    from app.domain.study import StudyLlmOutput

    corpo = "Parágrafo com conteúdo suficiente para passar no limite mínimo de tamanho do schema."
    texto = (
        '{"title": "CONFIE NELE", "body": ["' + corpo + '", "' + corpo + '", "' + corpo + '"]}, '
        '"application": ["Permita-se um momento de pausa hoje."], '
        '"prayer": ["Senhor, eu entrego a Ti. Amém."], '
        '"complementary_reading": {"candidate_index": 2, "reason": "Mostra o cuidado do pastor."}}, '
        '"keywords": ["confiança", "paz"]}'
    )
    obj = extract_json_object(texto)
    assert set(obj) == {"title", "body", "application", "prayer", "complementary_reading", "keywords"}
    out = StudyLlmOutput.model_validate(obj)
    assert out.application == "Permita-se um momento de pausa hoje."
    assert out.complementary_reading.candidate_index == 2


def test_repara_aspas_internas_sem_escape_caso_real_gemma():
    texto = '{"title": "PAZ", "n": 1, "nota": "a ideia de que "nada nos faltará" pode soar distante"}'
    obj = extract_json_object(texto)
    assert obj["nota"] == 'a ideia de que "nada nos faltará" pode soar distante'
    assert extract_json_object('{"title": "fim com aspas \\"ok\\"", "n": 2}')["n"] == 2
