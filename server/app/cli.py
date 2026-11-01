"""Linha de comando do servidor: `python -m app.cli <comando>`.

llm-check [--env-file infra/.env] [--saida json]
    Verifica o provedor LLM configurado (health) e gera um estudo de teste fixo (Salmos 23.1),
    mostrando provedor, modelo, tempo, tentativas, tokens e o JSON validado. Use sempre que trocar
    de provedor/modelo (docs/LLM_SERVER.md §5). Código de saída ≠ 0 em qualquer falha.
"""

import argparse
import asyncio
import datetime as dt
import json
import sys
from pathlib import Path

from app.core.config import Settings

PROMPTS = Path(__file__).resolve().parents[1] / "prompts"
DOCS = Path(__file__).resolve().parents[2] / "docs"


def openapi_json() -> str:
    from app.main import create_app

    return json.dumps(create_app().openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


# Estudo de teste fixo: referências apenas; o texto vem da BLIVRE quando o arquivo existe.
CHECK_VERSE = "Sl 23.1"
CHECK_CANDIDATES = ("Jo 10.11", "Is 40.11", "Ez 34.11-12", "1Pe 5.4", "Hb 13.20")


async def load_data(settings: Settings) -> int:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.domain.verse_plan import load_plan, plan_issues
    from app.services.content_data import sync_verse_plan

    if not settings.database_url:
        print("DATABASE_URL não configurada", file=sys.stderr)
        return 2
    plan = load_plan()
    if issues := plan_issues(plan):
        print("plano de versículos com problemas:\n" + "\n".join(issues), file=sys.stderr)
        return 1
    engine = create_async_engine(settings.database_url)
    try:
        async with async_sessionmaker(engine)() as session:
            r = await sync_verse_plan(session, plan)
    finally:
        await engine.dispose()
    print(f"plano de versículos: {len(plan)} entradas ({r.inserted} novas, {r.updated} alteradas, "
          f"{r.deactivated} desativadas)", file=sys.stderr)  # fmt: skip
    return 0


def load_prompt(name: str) -> tuple[str, str]:
    """Arquivo `prompts/<name>.md` com seções `# system` e `# user` → (system, user_template)."""
    text = (PROMPTS / f"{name}.md").read_text()
    text = "\n".join(line for line in text.splitlines() if not line.startswith("<!--"))
    _, rest = text.split("# system", 1)
    system, user = rest.split("# user", 1)
    return system.strip(), user.strip()


def _check_inputs(settings: Settings) -> tuple[str, str]:
    from app.bible.repository import BibleRepository

    try:
        bible = BibleRepository(settings.blivre_sqlite_path)
    except FileNotFoundError:
        default = Path(__file__).resolve().parents[2] / "tools/biblia/build/blivre.sqlite"
        bible = BibleRepository(default)
    passage = bible.get_passage(CHECK_VERSE)
    cands = "\n".join(f"{i}. {bible.get_passage(r).display}" for i, r in enumerate(CHECK_CANDIDATES))
    return f"{passage.display}|{passage.text}", cands


async def llm_check(settings: Settings, as_json: bool = False) -> int:
    from app.domain.study import StudyLlmOutput
    from app.llm import LlmError, get_llm_client

    client = get_llm_client(settings)
    health = await client.health()
    info = {"provider": client.provider, "model": client.model, "json_mode": settings.llm_json_mode}
    print(f"health: {'ok' if health.ok else 'FALHOU'} {health.detail} {info}", file=sys.stderr)
    if not health.ok:
        return 2
    verse, cands = _check_inputs(settings)
    ref, text = verse.split("|", 1)
    system, user_t = load_prompt("llm_check")
    user = user_t.format(data=dt.date.today().isoformat(), referencia=ref, texto=text, candidatos=cands)
    print(f"gerando estudo de teste ({ref}) — pode levar minutos com modelos locais...", file=sys.stderr)
    try:
        result = await client.generate_json(system=system, user=user, schema=StudyLlmOutput)
    except LlmError as exc:
        print(f"FALHOU: {type(exc).__name__}: {exc}", file=sys.stderr)
        if getattr(exc, "last_error", None):
            print(exc.last_error, file=sys.stderr)
        return 1
    summary = {
        **info,
        "duration_s": round(result.duration_s, 1),
        "attempts": result.attempts,
        "prompt_tokens": result.usage.prompt_tokens,
        "completion_tokens": result.usage.completion_tokens,
        "previous_errors": result.errors,
        "study": result.data.model_dump(),
    }
    if as_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        d = result.data
        print(f"OK em {summary['duration_s']} s, {result.attempts} tentativa(s), "
              f"{result.usage.prompt_tokens}+{result.usage.completion_tokens} tokens")  # fmt: skip
        print(f"\n{d.title}\n")
        for p in d.body:
            print(f"{p}\n")
        print(f"Aplicação: {d.application}\nOração: {d.prayer}")
        print(f"Leitura complementar: candidato {d.complementary_reading.candidate_index} "
              f"({d.complementary_reading.reason})\nPalavras-chave: {', '.join(d.keywords)}")  # fmt: skip
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    chk = sub.add_parser("llm-check", help="verifica o provedor LLM e gera um estudo de teste")
    chk.add_argument("--env-file", type=Path, help="lê as variáveis deste arquivo (ex.: infra/.env)")
    chk.add_argument("--saida", choices=["texto", "json"], default="texto")
    sub.add_parser("carregar-dados", help="sincroniza server/data/ com o banco")
    exp = sub.add_parser("export-openapi", help="grava docs/openapi.json")
    exp.add_argument("--saida", type=Path, default=DOCS / "openapi.json")
    args = ap.parse_args(argv)
    if args.cmd == "export-openapi":
        args.saida.write_text(openapi_json())
        print(f"OpenAPI gravado em {args.saida}", file=sys.stderr)
        return 0
    if args.cmd == "carregar-dados":
        return asyncio.run(load_data(Settings()))
    settings = Settings(_env_file=args.env_file) if args.env_file else Settings()
    if args.cmd == "llm-check":
        return asyncio.run(llm_check(settings, as_json=args.saida == "json"))
    return 2


if __name__ == "__main__":
    sys.exit(main())
