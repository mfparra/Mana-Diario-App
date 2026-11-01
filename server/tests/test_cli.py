import json

import pytest

from app import cli
from app.core.config import Settings
from app.llm.fake import FakeLlmClient

ESTUDO = {
    "title": "BOM PASTOR",
    "body": ["Parágrafo um com conteúdo suficiente para passar no limite mínimo de tamanho."] * 3,
    "application": "Confie hoje no cuidado de Deus.",
    "prayer": "Senhor, guia-me como meu pastor. Amém.",
    "complementary_reading": {"candidate_index": 0, "reason": "Jesus é o bom pastor."},
    "keywords": ["#Cuidado", "confiança"],
}


def test_prompt_de_verificacao_tem_secoes():
    system, user = cli.load_prompt("llm_check")
    assert "português do Brasil" in system
    assert "{referencia}" in user and "{candidatos}" in user


@pytest.mark.parametrize("saida_json", [False, True])
async def test_llm_check_com_fake(monkeypatch, capsys, saida_json):
    fake = FakeLlmClient([json.dumps(ESTUDO)])
    monkeypatch.setattr("app.llm.get_llm_client", lambda s: fake)
    monkeypatch.setattr(
        cli, "_check_inputs", lambda s: ("Salmos 23.1|O SENHOR é meu pastor.", "0. João 10.11")
    )
    assert await cli.llm_check(Settings(llm_provider="fake"), as_json=saida_json) == 0
    out = capsys.readouterr().out
    assert "BOM PASTOR" in out
    user = fake.calls[0][1]["content"]
    assert "Salmos 23.1" in user and "0. João 10.11" in user and "{" not in user
    if saida_json:
        assert json.loads(out)["study"]["keywords"] == ["cuidado", "confiança"]


async def test_llm_check_falha_com_codigo(monkeypatch):
    monkeypatch.setattr("app.llm.get_llm_client", lambda s: FakeLlmClient(["{}"] * 3))
    monkeypatch.setattr(cli, "_check_inputs", lambda s: ("Salmos 23.1|texto", "0. João 10.11"))
    assert await cli.llm_check(Settings(llm_provider="fake")) == 1
    monkeypatch.setattr("app.llm.get_llm_client", lambda s: FakeLlmClient(healthy=False))
    assert await cli.llm_check(Settings(llm_provider="fake")) == 2
