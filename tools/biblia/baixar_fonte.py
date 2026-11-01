"""Baixa (de novo) o zip USFM da BLIVRE da eBible.org e confere o SHA-256 registrado.

O zip já está versionado em `fonte/`; use este script só para conferir ou atualizar a fonte.
Se a eBible.org publicar uma revisão nova, o hash muda: o script avisa e não sobrescreve
sem `--aceitar-novo` (atualizar também `fonte/SHA256SUMS` e `DECISOES.md` B2).
"""

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

from blivre.importar import SOURCE_URL

FONTE = Path(__file__).resolve().parent / "fonte"
ZIP = FONTE / "porbr2018_usfm.zip"


def expected_sha() -> str:
    for line in (FONTE / "SHA256SUMS").read_text().splitlines():
        sha, name = line.split()
        if name == ZIP.name:
            return sha
    raise SystemExit("SHA256SUMS sem entrada para o zip")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--aceitar-novo", action="store_true", help="grava o zip mesmo se o hash mudou")
    args = ap.parse_args()
    with urllib.request.urlopen(SOURCE_URL, timeout=60) as resp:
        data = resp.read()
    sha = hashlib.sha256(data).hexdigest()
    if sha == expected_sha():
        ZIP.write_bytes(data)
        print(f"OK: {ZIP.name} confere ({sha})")
        return 0
    print(f"ATENÇÃO: hash diferente do registrado.\n  baixado:    {sha}\n  registrado: {expected_sha()}")
    if args.aceitar_novo:
        ZIP.write_bytes(data)
        (FONTE / "SHA256SUMS").write_text(f"{sha}  {ZIP.name}\n")
        print("Zip e SHA256SUMS atualizados — rode os testes e revise as diferenças.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
