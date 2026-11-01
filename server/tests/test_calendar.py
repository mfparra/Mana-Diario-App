import datetime as dt

import pytest

from app.domain.calendar import SPECIAL_DAYS, easter, special_dates, special_day_for, today

D = dt.date


@pytest.mark.parametrize(
    ("ano", "pascoa"),
    [(2025, D(2025, 4, 20)), (2026, D(2026, 4, 5)), (2027, D(2027, 3, 28)), (2030, D(2030, 4, 21)),
     (2019, D(2019, 4, 21)), (2024, D(2024, 3, 31)), (2038, D(2038, 4, 25)), (2285, D(2285, 3, 22))],
)  # fmt: skip
def test_pascoa(ano, pascoa):
    assert easter(ano) == pascoa


def test_pascoa_sempre_domingo_entre_22_mar_e_25_abr():
    for ano in range(1900, 2200):
        p = easter(ano)
        assert p.weekday() == 6
        assert D(ano, 3, 22) <= p <= D(ano, 4, 25)


def test_datas_de_2026():
    assert special_dates(2026) == {
        "cinzas": D(2026, 2, 18),
        "ramos": D(2026, 3, 29),
        "sexta_santa": D(2026, 4, 3),
        "pascoa": D(2026, 4, 5),
        "pentecostes": D(2026, 5, 24),
        "corpus_christi": D(2026, 6, 4),
        "maes": D(2026, 5, 10),
        "pais": D(2026, 8, 9),
        "natal": D(2026, 12, 25),
    }


def test_maes_e_pais_sao_segundo_domingo():
    for ano in range(2024, 2040):
        d = special_dates(ano)
        for chave, mes in (("maes", 5), ("pais", 8)):
            assert d[chave].weekday() == 6 and d[chave].month == mes and 8 <= d[chave].day <= 14


def test_special_day_for():
    assert special_day_for(D(2026, 6, 4)).key == "corpus_christi"
    assert special_day_for(D(2026, 12, 25)).name_pt == "Natal"
    assert special_day_for(D(2026, 6, 5)) is None


def test_prioridade_em_colisao():
    # Pentecostes 2008 = 11/05 = Dia das Mães (2º domingo de maio) → vale Pentecostes
    assert special_dates(2008)["pentecostes"] == special_dates(2008)["maes"] == D(2008, 5, 11)
    assert special_day_for(D(2008, 5, 11)).key == "pentecostes"
    assert [d.priority for d in SPECIAL_DAYS] == sorted(d.priority for d in SPECIAL_DAYS)


def test_hoje_em_sao_paulo():
    # 02:30 UTC de 01/11 ainda é 31/10 em São Paulo (UTC-3)
    assert today(dt.datetime(2026, 11, 1, 2, 30, tzinfo=dt.UTC)) == D(2026, 10, 31)
    assert today(dt.datetime(2026, 11, 1, 3, 0, tzinfo=dt.UTC)) == D(2026, 11, 1)
    with pytest.raises(ValueError):
        today(dt.datetime(2026, 11, 1))
