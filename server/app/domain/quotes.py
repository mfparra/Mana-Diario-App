"""Acervo de citações curadas (DECISOES P8/L5) e escolha da citação do dia.

Garantias (conferidas no carregamento e nos testes):
- toda citação tem autor e obra;
- `original` aparece LITERALMENTE no texto-fonte baixado (`server/data/citacoes_fontes/<fonte>.txt`);
- `texto` (exibição) só atualiza ortografia/pontuação final: mesmas palavras, mesma ordem.

Escolha: citações com tema do versículo do dia, não usadas na janela de repetição; sem tema compatível,
qualquer uma fora da janela; sem nenhuma → None (o app esconde a caixa).
"""

import csv
import datetime as dt
import difflib
import hashlib
import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data"  # server/data (no contêiner: /app/data)
DEFAULT_PATH = DATA / "quotes.csv"
SOURCES_DIR = DATA / "citacoes_fontes"
MAX_REPEAT_WINDOW_DAYS = 180


@dataclass(frozen=True)
class Quote:
    id: str
    tags: tuple[str, ...]
    author: str
    work: str
    source: str
    original: str
    text: str


class QuoteError(ValueError):
    pass


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("’", "'")).strip()


def _words(s: str) -> list[str]:
    plain = "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")
    return re.findall(r"[a-z]+", plain)


def _source_text(source: str, sources_dir: Path) -> str:
    path = sources_dir / f"{source}.txt"
    if not path.is_file():
        raise QuoteError(f"fonte {source!r} não encontrada em {sources_dir}")
    return _norm_ws(path.read_text().split("\n\n", 1)[-1])


def check_display_text(original: str, text: str) -> bool:
    """O texto de exibição tem as mesmas palavras do original (permite grafia atualizada)."""
    a, b = _words(original), _words(text)
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        if op != "replace":  # palavra inserida ou removida
            return False
        # trecho trocado precisa ser só grafia: "fallar"→"falar", "d antes"→"dantes", "acções"→"ações"
        old, new = "".join(a[i1:i2]), "".join(b[j1:j2])
        if difflib.SequenceMatcher(None, old, new).ratio() < 0.75:
            return False
    return True


def load_quotes(path: Path = DEFAULT_PATH, sources_dir: Path = SOURCES_DIR) -> list[Quote]:
    lines = [ln for ln in path.read_text().splitlines() if ln.strip() and not ln.startswith("#")]
    quotes: list[Quote] = []
    seen: set[str] = set()
    cache: dict[str, str] = {}
    for n, row in enumerate(csv.DictReader(lines), start=2):
        qid = row["id"].strip()
        author, work, source = row["autor"].strip(), row["obra"].strip(), row["fonte"].strip()
        original = _norm_ws(row["original"])
        text = _norm_ws(row["texto"]) or original
        if not qid or qid in seen:
            raise QuoteError(f"linha {n}: id vazio ou repetido ({qid!r})")
        if not author or not work:
            raise QuoteError(f"linha {n} ({qid}): citação sem autor ou obra")
        if source not in cache:
            cache[source] = _source_text(source, sources_dir)
        if original not in cache[source]:
            raise QuoteError(f"linha {n} ({qid}): 'original' não está literalmente na fonte {source}")
        if not check_display_text(original, text):
            raise QuoteError(f"linha {n} ({qid}): 'texto' muda palavras do original")
        tags = tuple(t.strip() for t in row["temas"].split("|") if t.strip())
        quotes.append(Quote(qid, tags, author, work, source, original, text))
        seen.add(qid)
    return quotes


def repeat_window(pool_size: int) -> int:
    """Janela de não repetição (em dias): uma citação usada há ≤ N dias fica de fora.
    Até 180, menor enquanto o acervo for pequeno."""
    return max(1, min(MAX_REPEAT_WINDOW_DAYS, int(pool_size * 0.8)))


def choose_quote(
    date: dt.date,
    themes: Sequence[str],
    quotes: Sequence[Quote],
    history: Iterable[tuple[dt.date, str]],
) -> Quote | None:
    """Citação para `date` dado o histórico [(data, id da citação)] — determinística."""
    if not quotes:
        return None
    last_use: dict[str, dt.date] = {}
    for d, qid in history:
        if d < date and (qid not in last_use or d > last_use[qid]):
            last_use[qid] = d
    limit = date - dt.timedelta(days=repeat_window(len(quotes)))
    free = [q for q in quotes if last_use.get(q.id, dt.date.min) < limit]
    wanted = {t.lower() for t in themes}
    matching = [q for q in free if wanted & {t.lower() for t in q.tags}]
    pool = matching or free
    if not pool:
        return None

    def rank(q: Quote) -> tuple[dt.date, str]:
        tie = hashlib.sha256(f"{date.isoformat()}:{q.id}".encode()).hexdigest()
        return (last_use.get(q.id, dt.date.min), tie)

    return min(pool, key=rank)
