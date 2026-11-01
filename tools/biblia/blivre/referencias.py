"""Parser e formatador de referências bíblicas em português do Brasil.

Aceita, por exemplo: "Sl 139.14", "Salmos 139:14", "1Co 13.4-7", "1 Coríntios 13", "Jo 3:16,18",
"I Coríntios 13", "Primeira Coríntios 13.1", "Gn 1.1-2.3", "Jo 3.16; 14.6", "Sl 1-2", "Jd 3".
Formata de volta no padrão do app: "Salmos 139.14", "1 Coríntios 13.4-7", "João 3.16,18".

Regras:
- Separador capítulo/versículo: "." ou ":" (saída sempre ".").
- "," continua no mesmo capítulo (versículos) ou lista capítulos se não houver versículo; ";" recomeça
  com capítulo.
- Livros de um capítulo só (Obadias, Filemom, 2 e 3 João, Judas): "Jd 3" = Judas 1.3.
- Validação aqui é sintática + número de capítulos; a existência do versículo é conferida na base.
"""

import re
import unicodedata
from dataclasses import dataclass

from blivre.livros import BOOKS, Book, book_by_usfm


class InvalidReferenceError(ValueError):
    """Referência inválida ou não reconhecida."""


@dataclass(frozen=True, order=True)
class VerseRange:
    chapter: int
    verse_start: int | None  # None = capítulo(s) inteiro(s)
    chapter_end: int
    verse_end: int | None

    @property
    def whole_chapters(self) -> bool:
        return self.verse_start is None


@dataclass(frozen=True)
class Reference:
    book: str  # código USFM
    ranges: tuple[VerseRange, ...]

    def __str__(self) -> str:
        return format_reference(self)


# --- normalização e índice de nomes ---------------------------------------------------------


def _key(s: str) -> str:
    return re.sub(r"[\s.]", "", unicodedata.normalize("NFC", s).casefold())


def _plain(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _base_forms(book: Book) -> list[str]:
    """Formas do nome sem o número do livro, incluindo o código USFM (1 Coríntios → Coríntios, Co, CO)."""
    strip_num = (lambda s: re.sub(r"^[123]\s*", "", s)) if book.number else (lambda s: s)
    return [strip_num(book.name_pt), strip_num(book.abbrev_pt), strip_num(book.usfm), *book.aliases]


def _build_index() -> tuple[dict[str, str], dict[str, str]]:
    exact: dict[str, str] = {}
    plain_candidates: dict[str, set[str]] = {}
    for book in BOOKS:
        prefix = str(book.number or "")
        for form in _base_forms(book):
            k = prefix + _key(form)
            if exact.get(k, book.usfm) != book.usfm:
                raise RuntimeError(f"Abreviação ambígua {k!r}: {exact[k]} e {book.usfm}")
            exact[k] = book.usfm
            plain_candidates.setdefault(_plain(k), set()).add(book.usfm)
    plain: dict[str, str] = {}
    for k, usfms in plain_candidates.items():
        if len(usfms) == 1:
            plain[k] = next(iter(usfms))
        elif k in exact:  # ex.: "jo" sem acento = João; "jó" com acento = Jó
            plain[k] = exact[k]
    return exact, plain


_EXACT, _PLAIN = _build_index()

_ORDINALS = {
    "i": 1,
    "ii": 2,
    "iii": 3,
    "primeiro": 1,
    "primeira": 1,
    "segundo": 2,
    "segunda": 2,
    "terceiro": 3,
    "terceira": 3,
}

_REF_RE = re.compile(
    r"""^\s*
    (?: (?P<num>[123])\s* | (?P<ord>iii|ii|i|primeir[oa]|segund[oa]|terceir[oa])\s+ )?
    (?P<name>[^\d\s][^\d]*?)\s*
    (?P<loc>\d[\d\s.:,;\-]*)?\s*$""",
    re.X | re.I,
)


def resolve_book(name: str, number: int | None = None) -> Book:
    """Nome/abreviação (sem o número) → livro. Levanta InvalidReferenceError se não reconhecer."""
    k = (str(number) if number else "") + _key(name)
    usfm = _EXACT.get(k) or _PLAIN.get(_plain(k))
    if usfm is None and len(_plain(_key(name))) >= 3:
        # prefixo único do nome completo: "Deuter", "Apocal", "Lament"
        p = _plain(k)
        hits = {
            b.usfm for b in BOOKS if (str(b.number or "") + _plain(_key(_base_forms(b)[0]))).startswith(p)
        }
        if len(hits) == 1:
            usfm = hits.pop()
    if usfm is None:
        shown = f"{number} {name}" if number else name
        raise InvalidReferenceError(f"Livro não reconhecido: {shown!r}")
    return book_by_usfm(usfm)


# --- parser -----------------------------------------------------------------------------------

_ITEM_RE = re.compile(r"^(\d+)(?:[.:](\d+))?(?:-(\d+)(?:[.:](\d+))?)?$")


def parse_reference(text: str) -> Reference:
    s = unicodedata.normalize("NFC", text).replace("–", "-").replace("—", "-")
    m = _REF_RE.match(s)
    if not m or not m.group("loc"):
        raise InvalidReferenceError(f"Referência inválida: {text!r}")
    number = int(m.group("num")) if m.group("num") else _ORDINALS.get((m.group("ord") or "").casefold())
    book = resolve_book(m.group("name"), number)
    ranges = _parse_location(m.group("loc"), book, text)
    return Reference(book.usfm, ranges)


def _parse_location(loc: str, book: Book, original: str) -> tuple[VerseRange, ...]:
    loc = re.sub(r"\s+", "", loc).strip(",;")
    if not loc:
        raise InvalidReferenceError(f"Referência sem capítulo: {original!r}")
    single = book.chapters == 1
    ranges: list[VerseRange] = []
    for segment in loc.split(";"):
        if not segment:
            raise InvalidReferenceError(f"Referência inválida: {original!r}")
        chapter: int | None = None  # capítulo corrente dentro do segmento
        verse_mode = False
        for idx, item in enumerate(segment.split(",")):
            im = _ITEM_RE.match(item)
            if not im:
                raise InvalidReferenceError(f"Trecho inválido {item!r} em {original!r}")
            a, b, c, d = (int(g) if g else None for g in im.groups())
            explicit = ":" in item or "." in item.split("-")[0]
            if idx == 0 or explicit or not verse_mode:
                if b is not None:  # C.V[-V2 | -C2.V2]
                    chapter = a
                    if c is None:
                        r = VerseRange(a, b, a, b)
                    elif d is None:
                        r = VerseRange(a, b, a, c)
                    else:
                        r = VerseRange(a, b, c, d)
                    verse_mode = True
                elif single:  # "Jd 3", "Jd 3-5"
                    chapter = 1
                    r = VerseRange(1, a, 1, c or a)
                    verse_mode = True
                elif c is not None and d is not None:  # "1-2.3": do capítulo 1 até 2.3
                    chapter = c
                    r = VerseRange(a, 1, c, d)
                    verse_mode = True
                else:  # capítulo(s) inteiro(s)
                    chapter = c or a
                    r = VerseRange(a, None, c or a, None)
            else:  # continuação de versículos no capítulo corrente: "16,18" / "16,18-20" / "4-5.2"
                assert chapter is not None
                if d is not None:
                    r = VerseRange(chapter, a, c, d)
                    chapter = c
                else:
                    r = VerseRange(chapter, a, chapter, c or a)
            _validate(r, book, original)
            ranges.append(r)
    return tuple(ranges)


def _validate(r: VerseRange, book: Book, original: str) -> None:
    for ch in (r.chapter, r.chapter_end):
        if not 1 <= ch <= book.chapters:
            raise InvalidReferenceError(f"{book.name_pt} tem {book.chapters} capítulo(s): {original!r}")
    if r.verse_start is not None and (r.verse_start < 1 or (r.verse_end or 0) < 1):
        raise InvalidReferenceError(f"Versículo inválido: {original!r}")
    start = (r.chapter, r.verse_start or 0)
    end = (r.chapter_end, r.verse_end or 0)
    if end < start:
        raise InvalidReferenceError(f"Intervalo invertido: {original!r}")


# --- formatador -------------------------------------------------------------------------------


def _fmt_range(r: VerseRange, with_chapter: bool, sep: str) -> str:
    if r.whole_chapters:
        return str(r.chapter) if r.chapter == r.chapter_end else f"{r.chapter}-{r.chapter_end}"
    start = f"{r.chapter}{sep}{r.verse_start}" if with_chapter else str(r.verse_start)
    if r.chapter_end != r.chapter:
        return f"{start}-{r.chapter_end}{sep}{r.verse_end}"
    if r.verse_end != r.verse_start:
        return f"{start}-{r.verse_end}"
    return start


def _fmt_location(ref: Reference, sep: str) -> str:
    out = ""
    prev: VerseRange | None = None
    for r in ref.ranges:
        if prev is None:
            out = _fmt_range(r, True, sep)
        elif not r.whole_chapters and not prev.whole_chapters and r.chapter == prev.chapter_end:
            out += "," + _fmt_range(r, False, sep)
        elif r.whole_chapters and prev.whole_chapters:
            out += "," + _fmt_range(r, True, sep)
        else:
            out += "; " + _fmt_range(r, True, sep)
        prev = r
    return out


def format_reference(ref: Reference, abbreviated: bool = False) -> str:
    """Reference → "Salmos 139.14" (ou "Sl 139.14" com `abbreviated=True`)."""
    book = book_by_usfm(ref.book)
    return f"{book.abbrev_pt if abbreviated else book.name_pt} {_fmt_location(ref, '.')}"


def format_canonical(ref: Reference) -> str:
    """Reference → forma canônica para armazenar/trafegar: "PSA 139:14", "1CO 13:4-7", "JHN 3:16; 14:6"."""
    return f"{ref.book} {_fmt_location(ref, ':')}"
