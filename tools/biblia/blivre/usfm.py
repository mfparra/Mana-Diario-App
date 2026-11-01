"""Parser do subconjunto de USFM usado pela BLIVRE da eBible.org (`porbr2018`).

Marcadores tratados:
- `\\id \\h \\toc1-3 \\mt1 \\ide \\p` — metadados/estrutura; `\\h` dá o nome do livro.
- `\\c N` capítulo, `\\v N texto` versículo (sempre em uma única linha nesta fonte).
- `\\d texto` — título de salmo (antes do versículo 1), guardado à parte.
- `\\add ...\\add*` — palavras acrescentadas pelos tradutores: as palavras ficam, os marcadores saem.
- `\\f + \\fr C:V \\fq trecho \\ft nota \\f*` — nota de rodapé, removida do texto e guardada à parte.
- `\\rq Ref \\rq*` — referência da citação (ex.: AT citado no NT), guardada como nota `quote_source`.

O texto bíblico **não é alterado**: só se removem marcadores e o espaço que eles deixam.
Qualquer marcador desconhecido gera erro, para não perder conteúdo em silêncio.
"""

import re
from dataclasses import dataclass, field

_SENTINEL = "\ue000"
_NOTE_RE = re.compile(r"\\f\s+\S\s+(.*?)\\f\*|\\rq\s+(.*?)\s*\\rq\*", re.S)
_KNOWN_LINE = {"id", "ide", "h", "toc1", "toc2", "toc3", "mt1", "p"}


class UsfmError(ValueError):
    pass


@dataclass
class Footnote:
    ordinal: int  # ordem dentro do versículo (0, 1, ...)
    position: int  # posição (em caracteres) no texto limpo onde a nota se aplica
    kind: str  # "note" | "quote_source"
    quote: str | None  # trecho do versículo a que a nota se refere (\fq)
    text: str


@dataclass
class Verse:
    chapter: int
    verse: int
    text: str
    footnotes: list[Footnote] = field(default_factory=list)


@dataclass
class ParsedBook:
    usfm: str
    name: str
    abbrev: str
    verses: list[Verse] = field(default_factory=list)
    superscriptions: dict[int, str] = field(default_factory=dict)

    @property
    def chapters(self) -> int:
        return max(v.chapter for v in self.verses)


def _collapse(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _parse_note(body: str) -> tuple[str | None, str]:
    """Corpo de `\\f ... \\f*` → (trecho \\fq, texto \\ft)."""
    body = re.sub(r"\\fr\s+\S+", "", body, count=1)
    quote = None
    m = re.search(r"\\fq\s+(.*?)(?=\\ft|$)", body, re.S)
    if m:
        quote = _collapse(m.group(1)) or None
        body = body[: m.start()] + body[m.end() :]
    text = _collapse(re.sub(r"\\ft\s*", " ", body))
    if "\\" in text or (quote and "\\" in quote):
        raise UsfmError(f"Marcador inesperado em nota: {body!r}")
    return quote, text


def clean_verse_text(raw: str) -> tuple[str, list[Footnote]]:
    """Remove marcadores de um versículo e devolve (texto limpo, notas)."""
    notes: list[tuple[str, str | None, str]] = []

    def take(m: re.Match[str]) -> str:
        if m.group(1) is not None:
            quote, text = _parse_note(m.group(1))
            notes.append(("note", quote, text))
        else:
            notes.append(("quote_source", None, _collapse(m.group(2))))
        return f" {_SENTINEL} "

    t = _NOTE_RE.sub(take, raw)
    # "\add dizendo\add* :" → "dizendo:" (o espaço antes da pontuação vem só do marcador)
    t = re.sub(r"\\add\*\s+(?=[,.;:!?])", "", t)
    t = re.sub(r"\\add\*", "", t)
    t = re.sub(r"\\add\s+", "", t)
    if "\\" in t:
        raise UsfmError(f"Marcador desconhecido no versículo: {raw!r}")
    parts = _collapse(t).split(_SENTINEL)

    # Junta os trechos entre notas sem deixar espaço duplo nem espaço antes de pontuação;
    # a posição da nota é o fim do texto que a precede.
    out = parts[0].strip()
    footnotes: list[Footnote] = []
    for (kind, quote, note_text), part in zip(notes, parts[1:], strict=True):
        footnotes.append(Footnote(len(footnotes), len(out), kind, quote, note_text))
        seg = part.strip()
        if seg:
            sep = " " if out and seg[0] not in ",.;:!?" else ""
            out = f"{out}{sep}{seg}"
    return out, footnotes


def parse_book(content: str) -> ParsedBook:
    usfm = name = abbrev = None
    book: ParsedBook | None = None
    chapter = 0
    for lineno, line in enumerate(content.splitlines(), start=1):
        line = line.strip().lstrip("\ufeff")
        if not line:
            continue
        m = re.match(r"\\(\w+)\s?(.*)$", line)
        if not m:
            raise UsfmError(f"Linha {lineno} sem marcador: {line[:60]!r}")
        tag, rest = m.group(1), m.group(2).strip()
        if tag == "id":
            usfm = rest.split()[0]
        elif tag == "h":
            name = rest
        elif tag == "toc3":
            abbrev = rest
        elif tag in _KNOWN_LINE:
            pass
        elif tag == "c":
            if book is None:
                if not (usfm and name and abbrev):
                    raise UsfmError("Cabeçalho do livro incompleto antes de \\c")
                book = ParsedBook(usfm, name, abbrev)
            chapter = int(rest)
        elif tag == "d":
            if book is None or chapter == 0:
                raise UsfmError(f"\\d fora de capítulo (linha {lineno})")
            book.superscriptions[chapter] = _collapse(re.sub(r"\\add\*|\\add\s+", "", rest))
        elif tag == "v":
            vm = re.match(r"(\d+)\s+(.*)$", rest, re.S)
            if book is None or not vm:
                raise UsfmError(f"Versículo inválido (linha {lineno}): {line[:60]!r}")
            text, footnotes = clean_verse_text(vm.group(2))
            book.verses.append(Verse(chapter, int(vm.group(1)), text, footnotes))
        else:
            raise UsfmError(f"Marcador de linha desconhecido \\{tag} (linha {lineno})")
    if book is None:
        raise UsfmError("Arquivo sem capítulos")
    return book
