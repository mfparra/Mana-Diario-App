"""Cânon protestante (66 livros) com códigos USFM, nomes e abreviações em pt-BR.

Nomes vêm da própria BLIVRE (`\\h`). Abreviações seguem o `\\toc3` da BLIVRE, exceto:
- JOB: a fonte usa "Jo" para Jó **e** para João; aqui Jó = "Jó" e João = "Jo".
- JOL: a fonte usa "Joel"; aqui "Jl" (padrão das abreviações curtas).
`aliases` são formas extras aceitas pelo parser de referências (sem o número do livro).
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Book:
    ordinal: int
    usfm: str
    name_pt: str
    abbrev_pt: str
    testament: str  # "OT" | "NT"
    chapters: int
    aliases: tuple[str, ...] = field(default=())

    @property
    def number(self) -> int | None:
        """Número do livro (1, 2, 3) para livros como 1 Samuel; None nos demais."""
        return int(self.usfm[0]) if self.usfm[0].isdigit() else None


_RAW: list[tuple[str, str, str, int, tuple[str, ...]]] = [
    ("GEN", "Gênesis", "Gn", 50, ("Gên", "Gen")),
    ("EXO", "Êxodo", "Ex", 40, ("Êx",)),
    ("LEV", "Levítico", "Lv", 27, ("Lev",)),
    ("NUM", "Números", "Nm", 36, ("Núm", "Num")),
    ("DEU", "Deuteronômio", "Dt", 34, ("Deut",)),
    ("JOS", "Josué", "Js", 24, ("Jos",)),
    ("JDG", "Juízes", "Jz", 21, ("Juí", "Jui")),
    ("RUT", "Rute", "Rt", 4, ()),
    ("1SA", "1 Samuel", "1Sm", 31, ("Sm", "Samuel", "Sam")),
    ("2SA", "2 Samuel", "2Sm", 24, ("Sm", "Samuel", "Sam")),
    ("1KI", "1 Reis", "1Rs", 22, ("Rs", "Reis")),
    ("2KI", "2 Reis", "2Rs", 25, ("Rs", "Reis")),
    ("1CH", "1 Crônicas", "1Cr", 29, ("Cr", "Crônicas", "Crôn")),
    ("2CH", "2 Crônicas", "2Cr", 36, ("Cr", "Crônicas", "Crôn")),
    ("EZR", "Esdras", "Esd", 10, ()),
    ("NEH", "Neemias", "Ne", 13, ("Nee",)),
    ("EST", "Ester", "Est", 10, ()),
    ("JOB", "Jó", "Jó", 42, ("Job",)),
    ("PSA", "Salmos", "Sl", 150, ("Salmo", "Sal", "Slm")),
    ("PRO", "Provérbios", "Pv", 31, ("Prv", "Prov")),
    ("ECC", "Eclesiastes", "Ec", 12, ("Ecl",)),
    ("SNG", "Cantares", "Ct", 8, ("Cânticos", "Cântico dos Cânticos", "Cantares de Salomão", "Cant")),
    ("ISA", "Isaías", "Is", 66, ()),
    ("JER", "Jeremias", "Jr", 52, ("Jer",)),
    ("LAM", "Lamentações", "Lm", 5, ("Lam",)),
    ("EZK", "Ezequiel", "Ez", 48, ("Ezeq",)),
    ("DAN", "Daniel", "Dn", 12, ("Dan",)),
    ("HOS", "Oseias", "Os", 14, ("Oséias",)),
    ("JOL", "Joel", "Jl", 3, ()),
    ("AMO", "Amós", "Am", 9, ()),
    ("OBA", "Obadias", "Ob", 1, ("Abdias", "Abd")),
    ("JON", "Jonas", "Jn", 4, ("Jon",)),
    ("MIC", "Miqueias", "Mq", 7, ("Miquéias", "Miq")),
    ("NAM", "Naum", "Na", 3, ()),
    ("HAB", "Habacuque", "Hab", 3, ("Hc",)),
    ("ZEP", "Sofonias", "Sf", 3, ("Sof",)),
    ("HAG", "Ageu", "Ag", 2, ()),
    ("ZEC", "Zacarias", "Zc", 14, ("Zac",)),
    ("MAL", "Malaquias", "Ml", 4, ("Mal",)),
    ("MAT", "Mateus", "Mt", 28, ("Mat",)),
    ("MRK", "Marcos", "Mc", 16, ("Mar",)),
    ("LUK", "Lucas", "Lc", 24, ("Luc",)),
    ("JHN", "João", "Jo", 21, ()),
    ("ACT", "Atos", "At", 28, ("Atos dos Apóstolos",)),
    ("ROM", "Romanos", "Rm", 16, ("Rom",)),
    ("1CO", "1 Coríntios", "1Co", 16, ("Co", "Coríntios", "Cor")),
    ("2CO", "2 Coríntios", "2Co", 13, ("Co", "Coríntios", "Cor")),
    ("GAL", "Gálatas", "Gl", 6, ("Gál",)),
    ("EPH", "Efésios", "Ef", 6, ("Efé",)),
    ("PHP", "Filipenses", "Fp", 4, ("Fl", "Fil")),
    ("COL", "Colossenses", "Cl", 4, ("Col",)),
    ("1TH", "1 Tessalonicenses", "1Ts", 5, ("Ts", "Tessalonicenses", "Tes")),
    ("2TH", "2 Tessalonicenses", "2Ts", 3, ("Ts", "Tessalonicenses", "Tes")),
    ("1TI", "1 Timóteo", "1Tm", 6, ("Tm", "Timóteo", "Tim")),
    ("2TI", "2 Timóteo", "2Tm", 4, ("Tm", "Timóteo", "Tim")),
    ("TIT", "Tito", "Tt", 3, ()),
    ("PHM", "Filemom", "Flm", 1, ("Fm", "Filemon", "Filêmon")),
    ("HEB", "Hebreus", "Hb", 13, ("Heb",)),
    ("JAS", "Tiago", "Tg", 5, ()),
    ("1PE", "1 Pedro", "1Pd", 5, ("Pd", "Pe", "Pedro", "Ped")),
    ("2PE", "2 Pedro", "2Pd", 3, ("Pd", "Pe", "Pedro", "Ped")),
    ("1JN", "1 João", "1Jo", 5, ("Jo", "João")),
    ("2JN", "2 João", "2Jo", 1, ("Jo", "João")),
    ("3JN", "3 João", "3Jo", 1, ("Jo", "João")),
    ("JUD", "Judas", "Jd", 1, ()),
    ("REV", "Apocalipse", "Ap", 22, ("Apoc", "Apocalipse de João")),
]

BOOKS: tuple[Book, ...] = tuple(
    Book(
        ordinal=i,
        usfm=usfm,
        name_pt=name,
        abbrev_pt=abbrev,
        testament="OT" if i <= 39 else "NT",
        chapters=chapters,
        aliases=aliases,
    )
    for i, (usfm, name, abbrev, chapters, aliases) in enumerate(_RAW, start=1)
)

_BY_USFM = {b.usfm: b for b in BOOKS}


def book_by_usfm(usfm: str) -> Book:
    try:
        return _BY_USFM[usfm.upper()]
    except KeyError:
        raise KeyError(f"Livro USFM desconhecido: {usfm!r}") from None
