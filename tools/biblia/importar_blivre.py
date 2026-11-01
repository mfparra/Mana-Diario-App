"""CLI: gera o blivre.sqlite a partir do zip USFM.

uv run python importar_blivre.py --entrada fonte/porbr2018_usfm.zip --saida build/blivre.sqlite
"""

import argparse
import sys
from pathlib import Path

from blivre.importar import build_database

AQUI = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--entrada", type=Path, default=AQUI / "fonte" / "porbr2018_usfm.zip")
    ap.add_argument("--saida", type=Path, default=AQUI / "build" / "blivre.sqlite")
    args = ap.parse_args(argv)
    r = build_database(args.entrada, args.saida)
    print(
        f"{args.saida}: {r.books} livros, {r.verses} versículos (fonte: {r.source_verse_markers}), "
        f"{r.footnotes} notas, {r.superscriptions} títulos de salmos; sha256 da fonte {r.sha256[:12]}…"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
