"""Exporta estudos publicados (JSON, um por linha, via psql) para um Markdown de revisão.

    distrobox-host-exec podman exec mana-db-1 psql -U manadiario -d manadiario -tAc \
      "select payload::text from studies where status='published' order by date" \
      | python3 server/scripts/exportar_amostras.py > docs/amostras/estudos_study_v1.md
"""

import json
import sys

print("# Amostras do prompt `study_v1` — revisão do Marcos (PLANO 3.6)\n")
print("Geradas automaticamente pelo worker (llm-server, Gemma 4 E4B). Versículos, leitura complementar e")
print("citações foram resolvidos pelo servidor (BLIVRE e acervo curado); o resto é da LLM.\n")
print("Para cada estudo: marque ✅ (ok), ✏️ (ajustar o prompt: diga o quê) ou ❌ (inaceitável).\n")
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    p = json.loads(line)
    sd = f" — {p['special_day']['name']}" if p.get("special_day") else ""
    print(f"---\n\n## {p['date']}{sd}: {p['title']}\n")
    print(f"**{p['verse']['display_ref']}** — {p['verse']['text']}\n")
    for par in p["body"]:
        print(f"{par}\n")
    print(f"**Aplicação:** {p['application']}\n")
    print(f"**Oração:** {p['prayer']}\n")
    q = p.get("quote")
    if q:
        print(f"> {q['text']}\n> — {q['author']}\n")
    c = p["complementary_reading"]
    print(f"**Leitura complementar:** {c['display_ref']} — {c['reason']}\n")
    print(f"**Palavras-chave:** {', '.join('#' + k for k in p['keywords'])}\n")
    print("Avaliação: ☐ ✅ ☐ ✏️ ☐ ❌ — comentário:\n")
