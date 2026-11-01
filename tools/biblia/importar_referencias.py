"""CLI: gera o crossrefs.sqlite (referências cruzadas do OpenBible.info) — usado só pelo servidor.

uv run python importar_referencias.py   # requer build/blivre.sqlite (importar_blivre.py antes)
"""

import argparse
import sys
from pathlib import Path

from blivre.referencias_cruzadas import build_crossrefs

AQUI = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--entrada", type=Path, default=AQUI / "fonte" / "openbible_cross-references.zip")
    ap.add_argument("--blivre", type=Path, default=AQUI / "build" / "blivre.sqlite")
    ap.add_argument("--saida", type=Path, default=AQUI / "build" / "crossrefs.sqlite")
    args = ap.parse_args(argv)
    r = build_crossrefs(args.entrada, args.blivre, args.saida)
    print(
        f"{args.saida}: {r.rows} referências (descartadas: {r.skipped_votes} com votos ≤ 0, "
        f"{r.skipped_missing} fora da BLIVRE); sha256 da fonte {r.sha256[:12]}…"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
