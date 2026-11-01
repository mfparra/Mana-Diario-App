"""Baixa os textos-fonte (domínio público) usados no acervo de citações e grava em
server/data/citacoes_fontes/<id>.txt (vão para a imagem do servidor junto com o quotes.csv).

Cada arquivo começa com um cabeçalho (URL, revisão, data) e depois o texto puro. As citações em
`server/data/quotes.csv` precisam aparecer LITERALMENTE no texto da fonte (teste em server/tests).

    python3 -I tools/citacoes/baixar_fontes.py [id ...]
"""

import datetime as dt
import html
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
DESTINO = AQUI.parents[1] / "server" / "data" / "citacoes_fontes"
UA = "mana-diario-curadoria/0.1"

# id → (autor, obra, wiki, título da página)
WS = "pt.wikisource.org"
FONTES: dict[str, tuple[str, str, str, str]] = {
    "vieira-sexagesima": (
        "Padre Antônio Vieira",
        "Sermão da Sexagésima (1655)",
        WS,
        "Sermões do padre Antonio Vieira/Sermão da Sexagesima",
    ),
    "vieira-santo-antonio": (
        "Padre Antônio Vieira",
        "Sermão de Santo Antônio aos Peixes (1654)",
        WS,
        "Sermão de Santo António (1654)",
    ),
    "vieira-mandato-1655": (
        "Padre Antônio Vieira",
        "Sermão do Mandato (1655)",
        WS,
        "Sermão do Mandato (1655)",
    ),
    "vieira-dominga-xix": (
        "Padre Antônio Vieira",
        "Sermão da Dominga XIX depois do Pentecoste",
        WS,
        "Sermão da Dominga XIX depois do Pentecoste",
    ),
}


def html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|sup)[^>]*>.*?</\1>", "", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</h\d>|</li>", "\n", raw)
    text = html.unescape(re.sub(r"<[^>]+>", "", raw))
    text = re.sub(r"[ \t ]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def fetch(wiki: str, title: str) -> tuple[str, int]:
    q = urllib.parse.urlencode({"action": "parse", "page": title, "prop": "text|revid", "format": "json",
                                "formatversion": "2", "redirects": "1"})  # fmt: skip
    req = urllib.request.Request(f"https://{wiki}/w/api.php?{q}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)["parse"]
    return html_to_text(data["text"]), data["revid"]


def main(ids: list[str]) -> int:
    for fid in ids or list(FONTES):
        autor, obra, wiki, title = FONTES[fid]
        text, revid = fetch(wiki, title)
        url = f"https://{wiki}/w/index.php?title={urllib.parse.quote(title.replace(' ', '_'))}&oldid={revid}"
        header = (f"# fonte: {fid}\n# autor: {autor}\n# obra: {obra}\n# url: {url}\n"
                  f"# licença: domínio público\n# baixado: {dt.date.today().isoformat()}\n\n")  # fmt: skip
        (DESTINO / f"{fid}.txt").write_text(header + text + "\n")
        print(f"{fid}: {len(text)} caracteres (rev {revid})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
