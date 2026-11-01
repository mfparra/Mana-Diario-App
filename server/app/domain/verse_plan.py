"""Plano de versículos (DECISOES P7) e escolha do versículo-base do dia (CONTEUDO_E_LLM.md §2).

Regras:
1. Data especial → um dos versículos daquela data; alterna entre os anos (o menos usado recentemente).
2. Dia comum → rodízio pela ordem do plano (temas intercalados), continuando do último usado e pulando
   o que já saiu nos últimos 365 dias. Com ≥ 366 entradas comuns, nunca repete dentro de um ano.
"""

import csv
import datetime as dt
import itertools
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from blivre import format_canonical, parse_reference

from app.domain.calendar import SPECIAL_DAYS, special_day_for

NO_REPEAT_DAYS = 365
DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "verse_plan.csv"
_SPECIAL_KEYS = {d.key for d in SPECIAL_DAYS}


@dataclass(frozen=True)
class PlanEntry:
    ref: str  # canônica USFM, ex.: "PSA 23:1"
    theme: str
    special_day: str | None


class PlanError(ValueError):
    pass


def _interleave(entries: list[PlanEntry]) -> list[PlanEntry]:
    """Ordena os dias comuns alternando os temas: tema1[0], tema2[0], ..., tema1[1], ..."""
    by_theme: dict[str, list[PlanEntry]] = {}
    for e in entries:
        by_theme.setdefault(e.theme, []).append(e)
    out: list[PlanEntry] = []
    i = 0
    while len(out) < len(entries):
        for items in by_theme.values():
            if i < len(items):
                out.append(items[i])
        i += 1
    return out


def load_plan(path: Path = DEFAULT_PATH) -> list[PlanEntry]:
    """Lê o CSV, normaliza as referências e devolve: dias comuns intercalados + datas especiais."""
    common: list[PlanEntry] = []
    special: list[PlanEntry] = []
    lines = [ln for ln in path.read_text().splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    for n, row in enumerate(csv.DictReader(lines), start=2):
        try:
            ref = format_canonical(parse_reference(row["ref"]))
        except ValueError as exc:
            raise PlanError(f"linha {n}: {exc}") from None
        day = (row.get("data_especial") or "").strip() or None
        if day is not None and day not in _SPECIAL_KEYS:
            raise PlanError(f"linha {n}: data especial desconhecida {day!r}")
        entry = PlanEntry(ref, row["tema"].strip(), day)
        (special if day else common).append(entry)
    return _interleave(common) + special


def plan_issues(entries: Sequence[PlanEntry]) -> list[str]:
    """Problemas de conteúdo (sem consultar a BLIVRE): repetição e sobreposição entre dias comuns."""
    issues: list[str] = []
    common = [e for e in entries if e.special_day is None]
    seen: dict[str, PlanEntry] = {}
    for e in common:
        if e.ref in seen:
            issues.append(f"repetido nos dias comuns: {e.ref} ({seen[e.ref].theme} e {e.theme})")
        seen[e.ref] = e
    # sobreposição: mesmo livro/capítulo com versículos que se cruzam (ex.: Mt 11.28 e Mt 11.28-30)
    spans: list[tuple[str, int, int, int, int, str]] = []
    for e in common:
        r = parse_reference(e.ref)
        for rg in r.ranges:
            s = (rg.chapter, rg.verse_start or 0)
            t = (rg.chapter_end, rg.verse_end or 999)
            spans.append((r.book, *s, *t, e.ref))
    spans.sort()
    for a, b in itertools.pairwise(spans):
        if a[0] == b[0] and (b[1], b[2]) <= (a[3], a[4]) and a[5] != b[5]:
            issues.append(f"sobreposição nos dias comuns: {a[5]} e {b[5]}")
    for key in sorted(_SPECIAL_KEYS):
        if not any(e.special_day == key for e in entries):
            issues.append(f"sem versículo para a data especial {key}")
    return issues


@dataclass(frozen=True)
class Choice:
    ref: str
    special_day: str | None
    theme: str


def choose_verse(
    date: dt.date, entries: Sequence[PlanEntry], history: Iterable[tuple[dt.date, str]]
) -> Choice:
    """Versículo-base para `date`, dado o histórico [(data, ref canônica)] dos estudos anteriores."""
    past = sorted((d, r) for d, r in history if d < date)
    last_use = {r: d for d, r in past}
    sd = special_day_for(date)
    if sd is not None:
        options = [e for e in entries if e.special_day == sd.key]
        if options:
            # o menos usado recentemente (nunca usado primeiro), empate pela ordem do plano
            best = min(options, key=lambda e: (last_use.get(e.ref, dt.date.min), options.index(e)))
            return Choice(best.ref, sd.key, best.theme)
    common = [e for e in entries if e.special_day is None]
    if not common:
        raise PlanError("plano sem versículos para dias comuns")
    index = {e.ref: i for i, e in enumerate(common)}
    last_common = next((index[r] for _, r in reversed(past) if r in index), -1)
    limit = date - dt.timedelta(days=NO_REPEAT_DAYS)
    for step in range(1, len(common) + 1):
        e = common[(last_common + step) % len(common)]
        used = last_use.get(e.ref)
        if used is None or used <= limit:
            return Choice(e.ref, None, e.theme)
    # plano menor que a janela: repete o mais antigo
    e = min(common, key=lambda x: last_use.get(x.ref, dt.date.min))
    return Choice(e.ref, None, e.theme)
