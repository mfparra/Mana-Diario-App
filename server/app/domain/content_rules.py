"""Regras automáticas de conteúdo do estudo (docs/CONTEUDO_E_LLM.md §4).

Os problemas voltam para a LLM na próxima tentativa, em português, como instrução de correção.
"""

import re
import unicodedata
from collections.abc import Callable, Sequence
from pathlib import Path

from blivre import parse_reference

from app.domain.study import StudyLlmOutput

BODY_WORDS = (200, 520)  # pedido no prompt: 250–450; margem para modelos pequenos
QUOTE_MIN_WORDS = 5
COPY_NGRAM = 8
BANNED_PATH = Path(__file__).resolve().parents[2] / "data" / "termos_proibidos.txt"

_QUOTED = re.compile(r"[\"“”«»]([^\"“”«»]{3,})[\"“”«»]|(?<![A-Za-zÀ-ÿ])'([^']{3,})'(?![A-Za-zÀ-ÿ])")
# "Jo 10.11", "1 Coríntios 13:4-7", "Salmos 23", "Sl 23.1,4"
_REF = re.compile(
    r"\b((?:[1-3]\s?|I{1,3}\s)?[A-ZÁÉÍÓÚÂÊÔ][a-záéíóúâêôãõç]{1,14}\.?)\s(\d{1,3})(?:[.:]\d{1,3}(?:\s?[-–]\s?\d{1,3})?(?:,\s?\d{1,3}(?!\d|\s?[A-ZÁÉÍÓÚÂÊÔ]))*)?"
)
# palavras muito frequentes em pt-BR, já sem acento (comparadas depois de _words)
_PT_STOPWORDS = frozenset(
    "de que o a e nao para com uma um voce seu sua em do da os as se por mais deus ele nos".split()  # noqa: SIM905
)


def _words(text: str) -> list[str]:
    plain = "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")
    return re.findall(r"[a-z0-9]+", plain)


def load_banned(path: Path = BANNED_PATH) -> list[str]:
    if not path.is_file():
        return []
    return [
        ln.strip().lower() for ln in path.read_text().splitlines() if ln.strip() and not ln.startswith("#")
    ]


def find_references(text: str) -> list[str]:
    """Trechos que parecem referência bíblica e cujo livro é reconhecido (o resto é ignorado)."""
    found = []
    for m in _REF.finditer(text):
        try:
            parse_reference(m.group(0))
        except ValueError as exc:
            if "Livro não reconhecido" in str(exc):
                continue  # "Capítulo 3", "Hoje 5" etc.
        found.append(m.group(0))
    return found


def validate_study(
    out: StudyLlmOutput,
    *,
    n_candidates: int,
    base_text: str,
    ref_exists: Callable[[str], bool],
    banned: Sequence[str] = (),
) -> list[str]:
    problems: list[str] = []
    if not 0 <= out.complementary_reading.candidate_index < n_candidates:
        problems.append(
            f"complementary_reading.candidate_index deve ser um dos números da lista (0 a {n_candidates - 1})"
        )
    texts = {"body": "\n".join(out.body), "application": out.application, "prayer": out.prayer}
    full = " ".join(texts.values())

    n_words = len(_words(texts["body"]))
    if not BODY_WORDS[0] <= n_words <= BODY_WORDS[1]:
        problems.append(f"o corpo tem {n_words} palavras; escreva entre 250 e 450")

    for field, text in texts.items():
        for m in _QUOTED.finditer(text):
            quoted = m.group(1) or m.group(2)
            if len(_words(quoted)) >= QUOTE_MIN_WORDS:
                problems.append(
                    f'{field}: não use citações entre aspas ("{quoted[:60]}…"); cite só a referência'
                )
                break

    base = _words(base_text)
    grams = {tuple(base[i : i + COPY_NGRAM]) for i in range(len(base) - COPY_NGRAM + 1)}
    words = _words(full)
    if any(tuple(words[i : i + COPY_NGRAM]) in grams for i in range(len(words) - COPY_NGRAM + 1)):
        problems.append(
            "não copie o texto do versículo-base; ele já aparece na tela — explique com suas palavras"
        )

    for ref in find_references(full):
        if not ref_exists(ref):
            problems.append(f"a referência {ref} não existe; use só referências reais ou não cite")

    lowered = full.lower()
    for term in banned:  # palavra/expressão inteira: "lula" não pega "célula"
        if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", lowered):
            problems.append(f'evite o termo/assunto "{term}"')

    sample = _words(full)
    if sample and sum(w in _PT_STOPWORDS for w in sample) / len(sample) < 0.12:
        problems.append("escreva em português do Brasil")
    return problems
