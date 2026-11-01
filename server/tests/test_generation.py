"""Pipeline de geração com FakeLlmClient (PLANO 3.7). Banco real + BLIVRE + referências cruzadas."""

import copy
import datetime as dt
import json
from pathlib import Path

import pytest
from blivre.importar import build_database
from blivre.referencias_cruzadas import build_crossrefs
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.bible.crossrefs import CrossReferenceRepository
from app.bible.repository import BibleRepository
from app.db.models import Study
from app.domain.content_rules import find_references, validate_study
from app.domain.quotes import load_quotes
from app.domain.study import StudyLlmOutput, StudyPayload
from app.domain.verse_plan import load_plan
from app.llm.fake import FakeLlmClient
from app.services.content_data import sync_quotes, sync_verse_plan
from app.services.generation import GenerationService

FONTE = Path(__file__).resolve().parents[2] / "tools/biblia/fonte"

P1 = (
    "Há dias em que acordamos cansados antes mesmo de começar. As contas, as notícias e as cobranças parecem "
    "maiores do que as nossas forças, e a alma fica pesada. É justamente aí que este versículo encontra "
    "você: "
    "ele não nega a dificuldade, mas lembra quem caminha ao seu lado e sustenta o que você não consegue "
    "carregar sozinho. A fé não é fingir que está tudo bem; é olhar para Deus no meio do que não está."
)
P2 = (
    "Na Bíblia, essa promessa foi feita a pessoas que conheciam o deserto, a espera e a perda. Elas não "
    "receberam uma vida sem problemas, e sim a certeza de uma presença fiel em cada etapa. Quando você lê "
    "esse texto hoje, receba-o do mesmo modo: como palavra para o caminho real, com tropeços e recomeços, "
    "e não como fórmula mágica. Deus continua sendo o pastor que conduz com paciência e cuida de perto."
)
P3 = (
    "Por isso, antes de correr para a próxima tarefa, pare um minuto. Respire, entregue a Ele o que pesa e "
    "peça sabedoria para o próximo passo, só o próximo. Você pode também conversar com alguém de confiança "
    "e pedir que ore com você. Pequenos gestos de confiança, repetidos ao longo do dia, vão abrindo espaço "
    "para a paz que não depende das circunstâncias. Leia também Jo 10.11 e lembre que você é conhecido "
    "pelo nome."
)
VALIDO = {
    "title": "Descanse nele",
    "body": [P1, P2, P3],
    "application": "Escolha um momento do seu dia para entregar a Deus, em oração, aquilo que mais pesa.",
    "prayer": "Senhor, tu conheces o meu cansaço. Ensina-me a confiar em ti a cada passo. Amém.",
    "complementary_reading": {
        "candidate_index": 0,
        "reason": "Mostra o cuidado do bom pastor por cada ovelha.",
    },
    "keywords": ["confiança", "descanso", "#Cuidado"],
}


def _resp(**changes) -> str:
    d = copy.deepcopy(VALIDO)
    d.update(changes)
    return json.dumps(d, ensure_ascii=False)


@pytest.fixture(scope="module")
def biblias(tmp_path_factory):
    d = tmp_path_factory.mktemp("dados")
    build_database(FONTE / "porbr2018_usfm.zip", d / "blivre.sqlite")
    build_crossrefs(FONTE / "openbible_cross-references.zip", d / "blivre.sqlite", d / "crossrefs.sqlite")
    bible = BibleRepository(d / "blivre.sqlite")
    xr = CrossReferenceRepository(d / "crossrefs.sqlite", bible)
    yield bible, xr
    xr.close()
    bible.close()


@pytest.fixture
async def ambiente(migrated_db_url, biblias):
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        await s.execute(text("DELETE FROM studies"))
        await s.commit()
        await sync_verse_plan(s, load_plan())
        await sync_quotes(s, load_quotes())
    bible, xr = biblias

    def service(session, respostas, tentativas=3):
        fake = FakeLlmClient(respostas, max_attempts=tentativas)
        return GenerationService(session, bible, xr, fake), fake

    yield maker, service, bible
    await engine.dispose()


DIA = dt.date(2026, 11, 3)  # dia comum


async def test_sucesso_publica_com_textos_do_servidor(ambiente):
    maker, service, bible = ambiente
    async with maker() as s:
        svc, fake = service(s, [_resp()])
        r = await svc.generate(DIA)
        assert (r.status, r.attempts) == ("published", 1)
        study = await s.get(Study, DIA)
        p = StudyPayload.model_validate(study.payload)
        assert study.status == "published" and study.etag and study.prompt_version == "study_v1"
        assert (study.provider, study.model) == ("fake", "fake-model")
        # versículo: texto da BLIVRE, nunca da LLM
        assert p.verse.text == bible.get_text(study.verse_ref)
        assert p.verse.translation == "BLIVRE"
        # leitura complementar resolvida a partir do índice
        assert bible.exists(p.complementary_reading.display_ref)
        # citação vem do acervo curado, com autor
        assert (
            p.quote is not None and p.quote.author == "Padre Antônio Vieira" and p.quote.source == "curated"
        )
        assert p.title == "DESCANSE NELE" and p.keywords == ["confiança", "descanso", "cuidado"]
        assert p.days_in_year == 365 and p.day_of_year == 307
        # o prompt levou o texto e os candidatos numerados
        user = fake.calls[0][1]["content"]
        assert bible.get_text(study.verse_ref)[:40] in user and "\n0. " in user


async def test_json_invalido_e_depois_valido(ambiente):
    maker, service, _ = ambiente
    async with maker() as s:
        svc, _ = service(s, ["isto não é json", '{"title": "X"}', _resp()])
        r = await svc.generate(DIA)
        assert (r.status, r.attempts) == ("published", 3)


async def test_ref_fora_dos_candidatos_pede_correcao(ambiente):
    maker, service, _ = ambiente
    fora = {"candidate_index": 99, "reason": "um candidato que não existe"}
    async with maker() as s:
        svc, fake = service(s, [_resp(complementary_reading=fora), _resp()])
        r = await svc.generate(DIA)
        assert (r.status, r.attempts) == ("published", 2)
        assert "candidate_index deve ser um dos números da lista" in fake.calls[1][1]["content"]


async def test_citacao_biblica_entre_aspas_no_corpo_pede_correcao(ambiente):
    maker, service, _ = ambiente
    com_aspas = [P1, P2 + ' Como está escrito: "O SENHOR é meu pastor, nada me faltará."', P3]
    async with maker() as s:
        svc, fake = service(s, [_resp(body=com_aspas), _resp()])
        r = await svc.generate(DIA)
        assert r.status == "published" and r.attempts == 2
        assert "não use citações entre aspas" in fake.calls[1][1]["content"]


async def test_falha_apos_3_tentativas_marca_failed(ambiente):
    maker, service, _ = ambiente
    async with maker() as s:
        svc, _ = service(s, ["{}", "{}", "{}"])
        r = await svc.generate(DIA)
        assert r.status == "failed" and r.attempts == 3 and "LlmInvalidOutput" in r.error
        study = await s.get(Study, DIA)
        assert study.status == "failed" and study.payload is None and study.verse_ref


async def test_nao_regera_publicado_sem_force_e_regera_com_force(ambiente):
    maker, service, _ = ambiente
    async with maker() as s:
        svc, _ = service(s, [_resp()])
        await svc.generate(DIA)
        svc2, fake2 = service(s, [_resp(title="Outro")])
        assert (await svc2.generate(DIA)).status == "skipped" and fake2.calls == []
        assert (await svc2.generate(DIA, force=True)).status == "published"
        assert (await s.get(Study, DIA)).payload["title"] == "OUTRO"


async def test_dias_seguidos_nao_repetem_versiculo_nem_citacao(ambiente):
    maker, service, _ = ambiente
    async with maker() as s:
        refs, citacoes = [], []
        for i in range(5):
            d = DIA + dt.timedelta(days=i)
            svc, _ = service(s, [_resp()])
            assert (await svc.generate(d)).status == "published"
            st = await s.get(Study, d)
            refs.append(st.verse_ref)
            citacoes.append(st.payload["quote"]["id"] if st.payload["quote"] else None)
        assert len(set(refs)) == 5
        assert len({c for c in citacoes if c}) == len([c for c in citacoes if c])


async def test_data_especial_usa_conjunto_e_marca_payload(ambiente):
    maker, service, _ = ambiente
    natal = dt.date(2026, 12, 25)
    async with maker() as s:
        svc, _ = service(s, [_resp()])
        assert (await svc.generate(natal)).status == "published"
        p = (await s.get(Study, natal)).payload
        assert p["special_day"] == {"key": "natal", "name": "Natal"}


# --- regras de conteúdo isoladas ------------------------------------------------------------------


def _out(**changes) -> StudyLlmOutput:
    return StudyLlmOutput.model_validate_json(_resp(**changes))


@pytest.mark.parametrize(
    ("mudanca", "trecho"),
    [
        ({"body": [P1, P2, P3 + " Leia Jo 99.1 também."]}, "não existe"),
        (
            {"body": [P1, P2, P3 + " O SENHOR é meu pastor nada me faltará deitar me faz em verdes pastos."]},
            "não copie o texto",
        ),
        ({"body": [P1[:300], P2[:300], P3[:300]]}, "palavras"),
        ({"prayer": "Senhor, eu declaro a cura garantida sobre a minha casa hoje. Amém."}, "cura garantida"),
    ],
)
def test_regras(mudanca, trecho):
    base = "O SENHOR é meu pastor, nada me faltará. Deitar-me faz em verdes pastos, guia-me mansamente."
    probs = validate_study(
        _out(**mudanca), n_candidates=3, base_text=base, ref_exists=lambda r: "99" not in r,
        banned=["cura garantida", "lula"],
    )  # fmt: skip
    assert any(trecho in p for p in probs), probs


def test_termo_proibido_e_palavra_inteira():
    prayer = "Senhor, cuida de cada célula do meu corpo e da minha família. Amém."
    probs = validate_study(_out(prayer=prayer), n_candidates=3, base_text="x", ref_exists=lambda r: True,
                           banned=["lula"])  # fmt: skip
    assert probs == []


def test_encontra_referencias():
    assert find_references("Leia Jo 10.11, 1 Coríntios 13:4-7 e Salmos 23; no capítulo 3 de hoje.") == [
        "Jo 10.11",
        "1 Coríntios 13:4-7",
        "Salmos 23",
    ]
