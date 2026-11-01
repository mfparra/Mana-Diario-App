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

DOCS = Path(__file__).resolve().parents[2] / "docs"


def openapi_json() -> str:
    from app.main import create_app

    return json.dumps(create_app().openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


# Estudo de teste fixo: referências apenas; o texto vem da BLIVRE quando o arquivo existe.
CHECK_VERSE = "Sl 23.1"
CHECK_CANDIDATES = ("Jo 10.11", "Is 40.11", "Ez 34.11-12", "1Pe 5.4", "Hb 13.20")


async def generate_dates(settings: Settings, dates: list[dt.date], force: bool) -> int:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.bible.crossrefs import CrossReferenceRepository
    from app.bible.repository import BibleRepository
    from app.llm import get_llm_client
    from app.services.generation import GenerationService

    if not settings.database_url:
        print("DATABASE_URL não configurada", file=sys.stderr)
        return 2
    bible = BibleRepository(settings.blivre_sqlite_path)
    xr = CrossReferenceRepository(settings.crossrefs_sqlite_path, bible)
    llm = get_llm_client(settings)
    engine = create_async_engine(settings.database_url)
    falhas = 0
    try:
        for d in dates:
            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                r = await GenerationService(session, bible, xr, llm).generate(d, force=force)
            falhas += r.status == "failed"
            extra = f" — {r.error}" if r.error else ""
            print(f"{d}: {r.status} ({r.verse_ref}, {r.attempts} tentativa(s)){extra}", file=sys.stderr)
    finally:
        await engine.dispose()
    return 1 if falhas else 0


async def load_data(settings: Settings) -> int:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.domain.quotes import load_quotes
    from app.domain.verse_plan import load_plan, plan_issues
    from app.services.content_data import sync_quotes, sync_verse_plan

    if not settings.database_url:
        print("DATABASE_URL não configurada", file=sys.stderr)
        return 2
    plan = load_plan()
    if issues := plan_issues(plan):
        print("plano de versículos com problemas:\n" + "\n".join(issues), file=sys.stderr)
        return 1
    quotes = load_quotes()  # recusa citação sem fonte literal
    engine = create_async_engine(settings.database_url)
    try:
        async with async_sessionmaker(engine)() as session:
            r = await sync_verse_plan(session, plan)
            rq = await sync_quotes(session, quotes)
    finally:
        await engine.dispose()
    for nome, total, rep in (("plano de versículos", len(plan), r), ("citações", len(quotes), rq)):
        print(f"{nome}: {total} entradas ({rep.inserted} novas, {rep.updated} alteradas, "
              f"{rep.deactivated} desativadas)", file=sys.stderr)  # fmt: skip
    return 0


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
    from app.services.generation import load_prompt

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
    ger = sub.add_parser("gerar", help="gera e publica estudos")
    ger.add_argument("--data", type=dt.date.fromisoformat)
    ger.add_argument("--de", type=dt.date.fromisoformat)
    ger.add_argument("--ate", type=dt.date.fromisoformat)
    ger.add_argument("--force", action="store_true", help="regera mesmo se já publicado")
    sub.add_parser("carregar-dados", help="sincroniza server/data/ com o banco")
    exp = sub.add_parser("export-openapi", help="grava docs/openapi.json")
    exp.add_argument("--saida", type=Path, default=DOCS / "openapi.json")
    args = ap.parse_args(argv)
    if args.cmd == "export-openapi":
        args.saida.write_text(openapi_json())
        print(f"OpenAPI gravado em {args.saida}", file=sys.stderr)
        return 0
    if args.cmd == "gerar":
        if args.data:
            dates = [args.data]
        elif args.de and args.ate and args.de <= args.ate:
            dates = [args.de + dt.timedelta(days=i) for i in range((args.ate - args.de).days + 1)]
        else:
            ap.error("use --data ou --de/--ate (com de ≤ ate)")
        return asyncio.run(generate_dates(Settings(), dates, args.force))
    if args.cmd == "carregar-dados":
        return asyncio.run(load_data(Settings()))
    settings = Settings(_env_file=args.env_file) if args.env_file else Settings()
    if args.cmd == "llm-check":
        return asyncio.run(llm_check(settings, as_json=args.saida == "json"))
    return 2


if __name__ == "__main__":
    sys.exit(main())
