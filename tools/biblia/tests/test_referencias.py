import pytest

from blivre.livros import BOOKS
from blivre.referencias import (
    InvalidReferenceError,
    Reference,
    VerseRange,
    format_canonical,
    format_reference,
    parse_reference,
)


def R(book: str, *ranges: tuple[int, int | None, int, int | None]) -> Reference:
    return Reference(book, tuple(VerseRange(*r) for r in ranges))


CASOS = [
    # formatos pedidos no PLANO 1.3
    ("Sl 139.14", R("PSA", (139, 14, 139, 14))),
    ("Salmos 139:14", R("PSA", (139, 14, 139, 14))),
    ("1Co 13.4-7", R("1CO", (13, 4, 13, 7))),
    ("1 Coríntios 13", R("1CO", (13, None, 13, None))),
    ("Jo 3:16,18", R("JHN", (3, 16, 3, 16), (3, 18, 3, 18))),
    # abreviações da BLIVRE (\toc3) e do app
    ("Gn 1.1", R("GEN", (1, 1, 1, 1))),
    ("Ex 20.3", R("EXO", (20, 3, 20, 3))),
    ("Lv 19.18", R("LEV", (19, 18, 19, 18))),
    ("Nm 6.24-26", R("NUM", (6, 24, 6, 26))),
    ("Dt 6.4", R("DEU", (6, 4, 6, 4))),
    ("Js 1.9", R("JOS", (1, 9, 1, 9))),
    ("1Sm 16.7", R("1SA", (16, 7, 16, 7))),
    ("2Sm 22.2", R("2SA", (22, 2, 22, 2))),
    ("1Rs 19.12", R("1KI", (19, 12, 19, 12))),
    ("2Cr 7.14", R("2CH", (7, 14, 7, 14))),
    ("Jó 19.25", R("JOB", (19, 25, 19, 25))),
    ("Pv 3.5-6", R("PRO", (3, 5, 3, 6))),
    ("Prv 3.5", R("PRO", (3, 5, 3, 5))),
    ("Is 40.31", R("ISA", (40, 31, 40, 31))),
    ("Jr 29.11", R("JER", (29, 11, 29, 11))),
    ("Lm 3.22-23", R("LAM", (3, 22, 3, 23))),
    ("Mq 6.8", R("MIC", (6, 8, 6, 8))),
    ("Hab 3.17", R("HAB", (3, 17, 3, 17))),
    ("Mt 5.3-12", R("MAT", (5, 3, 5, 12))),
    ("Mc 10.45", R("MRK", (10, 45, 10, 45))),
    ("Lc 15", R("LUK", (15, None, 15, None))),
    ("At 2.38", R("ACT", (2, 38, 2, 38))),
    ("Rm 8.28", R("ROM", (8, 28, 8, 28))),
    ("2Co 5.17", R("2CO", (5, 17, 5, 17))),
    ("Gl 5.22-23", R("GAL", (5, 22, 5, 23))),
    ("Ef 2.8-9", R("EPH", (2, 8, 2, 9))),
    ("Fp 4.13", R("PHP", (4, 13, 4, 13))),
    ("1Ts 5.17", R("1TH", (5, 17, 5, 17))),
    ("2Tm 3.16", R("2TI", (3, 16, 3, 16))),
    ("Hb 11.1", R("HEB", (11, 1, 11, 1))),
    ("Tg 1.5", R("JAS", (1, 5, 1, 5))),
    ("1Pd 5.7", R("1PE", (5, 7, 5, 7))),
    ("1Jo 4.8", R("1JN", (4, 8, 4, 8))),
    ("Ap 21.4", R("REV", (21, 4, 21, 4))),
    # livros numerados escritos de vários jeitos
    ("1 Jo 1.9", R("1JN", (1, 9, 1, 9))),
    ("I Coríntios 13.13", R("1CO", (13, 13, 13, 13))),
    ("II Reis 2.11", R("2KI", (2, 11, 2, 11))),
    ("Primeira Coríntios 10.13", R("1CO", (10, 13, 10, 13))),
    ("Segundo Samuel 7.12", R("2SA", (7, 12, 7, 12))),
    ("3 João 1.2", R("3JN", (1, 2, 1, 2))),
    ("1 Tessalonicenses 4.16-17", R("1TH", (4, 16, 4, 17))),
    # nomes completos, sem acento, maiúsculas, ponto na abreviação, espaços
    ("João 14.6", R("JHN", (14, 6, 14, 6))),
    ("joao 14:6", R("JHN", (14, 6, 14, 6))),
    ("GÊNESIS 1:1", R("GEN", (1, 1, 1, 1))),
    ("Gên. 1.27", R("GEN", (1, 27, 1, 27))),
    ("1co 13 : 4 - 7", R("1CO", (13, 4, 13, 7))),
    ("Cântico dos Cânticos 2.4", R("SNG", (2, 4, 2, 4))),
    ("Ct 8.6", R("SNG", (8, 6, 8, 6))),
    ("Deuter 31.6", R("DEU", (31, 6, 31, 6))),  # prefixo único
    ("Filipenses 4.6–7", R("PHP", (4, 6, 4, 7))),  # travessão
    # intervalos e listas
    ("Gn 1.1-2.3", R("GEN", (1, 1, 2, 3))),
    ("Sl 1-2", R("PSA", (1, None, 2, None))),
    ("Sl 1,2", R("PSA", (1, None, 1, None), (2, None, 2, None))),
    ("Jo 3.16; 14.6", R("JHN", (3, 16, 3, 16), (14, 6, 14, 6))),
    ("Rm 8.28,31-39", R("ROM", (8, 28, 8, 28), (8, 31, 8, 39))),
    ("Jo 3.16,4.1", R("JHN", (3, 16, 3, 16), (4, 1, 4, 1))),
    ("Sl 23; 24.1", R("PSA", (23, None, 23, None), (24, 1, 24, 1))),
    # livros de um só capítulo
    ("Jd 3", R("JUD", (1, 3, 1, 3))),
    ("Judas 24-25", R("JUD", (1, 24, 1, 25))),
    ("Filemom 1.6", R("PHM", (1, 6, 1, 6))),
    ("Ob 15", R("OBA", (1, 15, 1, 15))),
]


@pytest.mark.parametrize(("texto", "esperado"), CASOS)
def test_parse(texto, esperado):
    assert parse_reference(texto) == esperado


def test_tem_pelo_menos_40_casos():
    assert len(CASOS) >= 40


@pytest.mark.parametrize(
    ("texto", "formatado", "abreviado"),
    [
        ("Sl 139:14", "Salmos 139.14", "Sl 139.14"),
        ("1co 13.4-7", "1 Coríntios 13.4-7", "1Co 13.4-7"),
        ("Jo 3:16,18", "João 3.16,18", "Jo 3.16,18"),
        ("1 Coríntios 13", "1 Coríntios 13", "1Co 13"),
        ("Gn 1.1-2.3", "Gênesis 1.1-2.3", "Gn 1.1-2.3"),
        ("Jo 3.16; 14.6", "João 3.16; 14.6", "Jo 3.16; 14.6"),
        ("Sl 23; 24.1", "Salmos 23; 24.1", "Sl 23; 24.1"),
        ("Sl 1,2", "Salmos 1,2", "Sl 1,2"),
        ("Jó 1.1", "Jó 1.1", "Jó 1.1"),
        ("Jd 3", "Judas 1.3", "Jd 1.3"),
    ],
)
def test_formatar(texto, formatado, abreviado):
    ref = parse_reference(texto)
    assert format_reference(ref) == formatado
    assert format_reference(ref, abbreviated=True) == abreviado
    assert str(ref) == formatado


@pytest.mark.parametrize("texto", [t for t, _ in CASOS])
def test_ida_e_volta(texto):
    ref = parse_reference(texto)
    assert parse_reference(format_reference(ref)) == ref
    assert parse_reference(format_reference(ref, abbreviated=True)) == ref


@pytest.mark.parametrize(
    "texto",
    [
        "",
        "Salmos",  # sem capítulo
        "Xyz 1.1",  # livro inexistente
        "Sl 151",  # Salmos tem 150
        "Jo 22.1",  # João tem 21
        "Jo 3.18-16",  # invertido
        "Jo 3.0",
        "Samuel 3.1",  # falta o número do livro
        "4 Reis 1.1",
        "Jo 3..16",
        "Jo 3.16;;4",
    ],
)
def test_invalidas(texto):
    with pytest.raises(InvalidReferenceError):
        parse_reference(texto)


@pytest.mark.parametrize(
    ("texto", "canonico"),
    [
        ("Sl 139.14", "PSA 139:14"),
        ("1 Coríntios 13.4-7", "1CO 13:4-7"),
        ("Jo 3:16,18", "JHN 3:16,18"),
        ("Jo 3.16; 14.6", "JHN 3:16; 14:6"),
        ("Gn 1.1-2.3", "GEN 1:1-2:3"),
        ("Sl 23", "PSA 23"),
        ("Jd 3", "JUD 1:3"),
    ],
)
def test_forma_canonica_ida_e_volta(texto, canonico):
    ref = parse_reference(texto)
    assert format_canonical(ref) == canonico
    assert parse_reference(canonico) == ref


@pytest.mark.parametrize("usfm", [b.usfm for b in BOOKS])
def test_todo_codigo_usfm_e_aceito(usfm):
    assert parse_reference(f"{usfm} 1").book == usfm
