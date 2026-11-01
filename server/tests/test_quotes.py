import datetime as dt

import pytest

from app.domain.quotes import (
    Quote,
    QuoteError,
    check_display_text,
    choose_quote,
    load_quotes,
    repeat_window,
)


@pytest.fixture(scope="module")
def acervo():
    return load_quotes()


def test_acervo_carrega_e_toda_citacao_tem_autor_e_fonte(acervo):
    assert len(acervo) >= 20
    for q in acervo:
        assert q.author.strip() and q.work.strip() and q.source
        assert q.tags, q.id


def test_original_literal_na_fonte(tmp_path):
    (tmp_path / "f.txt").write_text("# cabeçalho\n\nNo princípio era o Verbo, e o Verbo estava com Deus.\n")
    csv = tmp_path / "q.csv"
    csv.write_text("id,temas,autor,obra,fonte,original,texto\nq1,fé,Autor,Obra,f,o Verbo estava com Deus,\n")
    assert load_quotes(csv, tmp_path)[0].text == "o Verbo estava com Deus"
    csv.write_text(
        "id,temas,autor,obra,fonte,original,texto\nq1,fé,Autor,Obra,f,o Verbo estava com os anjos,\n"
    )
    with pytest.raises(QuoteError, match="literalmente"):
        load_quotes(csv, tmp_path)
    csv.write_text("id,temas,autor,obra,fonte,original,texto\nq1,fé,,Obra,f,o Verbo estava com Deus,\n")
    with pytest.raises(QuoteError, match="sem autor"):
        load_quotes(csv, tmp_path)


@pytest.mark.parametrize(
    ("original", "texto", "ok"),
    [
        ("Para fallar ao vento, bastam palavras", "Para falar ao vento, bastam palavras.", True),
        ("do que d’antes era", "do que dantes era", True),
        ("Para fallar ao vento, bastam palavras", "Para falar ao mar, bastam frases", False),
        ("Deus ama-os pelo bem que lhes faz", "Deus ama-os pelo mal que lhes faz", False),
        ("Ama Cristo enquanto homem", "Ama Cristo enquanto homem e também como Deus eterno", False),
    ],
)
def test_texto_de_exibicao_so_atualiza_grafia(original, texto, ok):
    assert check_display_text(original, texto) is ok


def _q(i: int, *tags: str) -> Quote:
    return Quote(f"q{i}", tags, "Autor", "Obra", "f", "x", f"citação {i}")


def test_escolha_por_tema_e_deterministica():
    acervo = [_q(1, "fé"), _q(2, "paz"), _q(3, "paz"), _q(4, "amor")]
    d = dt.date(2026, 11, 1)
    a = choose_quote(d, ["paz"], acervo, [])
    assert a.id in {"q2", "q3"}
    assert choose_quote(d, ["paz"], acervo, []) == a  # mesma data → mesma citação
    outra = choose_quote(d, ["paz"], acervo, [(d - dt.timedelta(days=1), a.id)])
    assert outra.id in {"q2", "q3"} - {a.id}  # a usada ontem fica de fora


def test_sem_tema_compativel_usa_qualquer_livre_e_sem_livre_devolve_none():
    acervo = [_q(1, "fé"), _q(2, "paz")]
    d = dt.date(2026, 11, 10)
    assert choose_quote(d, ["trabalho"], acervo, []) is not None
    hist = [(d - dt.timedelta(days=1), "q1"), (d - dt.timedelta(days=1), "q2")]
    assert repeat_window(len(acervo)) == 1
    assert choose_quote(d, ["fé"], acervo, hist) is None  # janela de 1 dia: as duas usadas ontem
    assert choose_quote(d, ["fé"], [], []) is None


def test_janela_de_repeticao_cresce_com_o_acervo():
    assert repeat_window(23) == 18
    assert repeat_window(500) == 180


def test_simulacao_sem_repetir_dentro_da_janela(acervo):
    hist: list[tuple[dt.date, str]] = []
    janela = repeat_window(len(acervo))
    temas = ["amor de Deus", "Palavra", "esperança", "serviço", "graça", "trabalho"]
    for i in range(200):
        d = dt.date(2027, 1, 1) + dt.timedelta(days=i)
        q = choose_quote(d, [temas[i % len(temas)]], acervo, hist)
        if q is None:
            continue
        ultimo = max((h for h in hist if h[1] == q.id), default=None)
        if ultimo:
            assert (d - ultimo[0]).days > janela
        hist.append((d, q.id))
    assert len({qid for _, qid in hist}) == len(acervo)  # todas acabam usadas


async def test_sincroniza_citacoes_com_o_banco(migrated_db_url, acervo):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.services.content_data import sync_quotes

    engine = create_async_engine(migrated_db_url)
    async with async_sessionmaker(engine)() as s:
        await s.execute(text("UPDATE studies SET quote_id = NULL"))
        await s.execute(text("DELETE FROM curated_quotes"))
        await s.commit()
        r = await sync_quotes(s, acervo)
        assert r.inserted == len(acervo)
        assert (await sync_quotes(s, acervo)).updated == 0
        sem_autor = (await s.execute(text("SELECT count(*) FROM curated_quotes WHERE author = ''"))).scalar()
        assert sem_autor == 0
    await engine.dispose()
