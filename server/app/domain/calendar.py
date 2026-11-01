"""Calendário de datas especiais (docs/CONTEUDO_E_LLM.md §2). Datas no fuso America/Sao_Paulo.

Páscoa pelo computus gregoriano (algoritmo anônimo / Meeus–Jones–Butcher); datas móveis derivadas dela.
Se duas datas caírem no mesmo dia, vale a de maior prioridade (litúrgicas antes das civis).
"""

import datetime as dt
from dataclasses import dataclass
from functools import lru_cache
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")


@dataclass(frozen=True)
class SpecialDay:
    key: str
    name_pt: str
    priority: int  # menor = mais importante


# Ordem = prioridade.
SPECIAL_DAYS: tuple[SpecialDay, ...] = (
    SpecialDay("pascoa", "Domingo de Páscoa", 0),
    SpecialDay("sexta_santa", "Sexta-feira Santa", 1),
    SpecialDay("natal", "Natal", 2),
    SpecialDay("pentecostes", "Pentecostes", 3),
    SpecialDay("ramos", "Domingo de Ramos", 4),
    SpecialDay("cinzas", "Quarta-feira de Cinzas", 5),
    SpecialDay("corpus_christi", "Corpus Christi", 6),
    SpecialDay("maes", "Dia das Mães", 7),
    SpecialDay("pais", "Dia dos Pais", 8),
)
_BY_KEY = {d.key: d for d in SPECIAL_DAYS}


def easter(year: int) -> dt.date:
    """Domingo de Páscoa (calendário gregoriano)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741 — nome do algoritmo original
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return dt.date(year, month, day + 1)


def nth_sunday(year: int, month: int, n: int) -> dt.date:
    first = dt.date(year, month, 1)
    first_sunday = first + dt.timedelta(days=(6 - first.weekday()) % 7)
    return first_sunday + dt.timedelta(weeks=n - 1)


def special_dates(year: int) -> dict[str, dt.date]:
    """Chave → data, para o ano."""
    p = easter(year)
    return {
        "cinzas": p - dt.timedelta(days=46),
        "ramos": p - dt.timedelta(days=7),
        "sexta_santa": p - dt.timedelta(days=2),
        "pascoa": p,
        "pentecostes": p + dt.timedelta(days=49),
        "corpus_christi": p + dt.timedelta(days=60),
        "maes": nth_sunday(year, 5, 2),
        "pais": nth_sunday(year, 8, 2),
        "natal": dt.date(year, 12, 25),
    }


@lru_cache(maxsize=256)
def _by_date(year: int) -> dict[dt.date, str]:
    out: dict[dt.date, str] = {}
    for key, date in sorted(
        special_dates(year).items(), key=lambda kv: _BY_KEY[kv[0]].priority, reverse=True
    ):
        out[date] = key  # a de maior prioridade sobrescreve
    return out


def special_day_for(date: dt.date) -> SpecialDay | None:
    key = _by_date(date.year).get(date)
    return _BY_KEY[key] if key else None


def today(now: dt.datetime | None = None) -> dt.date:
    """O "hoje" do estudo: data civil em America/Sao_Paulo."""
    now = now or dt.datetime.now(dt.UTC)
    if now.tzinfo is None:
        raise ValueError("now precisa ter fuso horário")
    return now.astimezone(TZ).date()
