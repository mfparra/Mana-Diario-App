"""Pipeline de geração do estudo diário (docs/CONTEUDO_E_LLM.md §4):

    escolher versículo (calendário > plano) → texto da BLIVRE → citação curada → candidatos de leitura
    → prompt → LLM (JSON validado + regras de conteúdo, até LLM_MAX_RETRIES) → payload com textos
    resolvidos pelo servidor → publicar (DECISOES L8) ou marcar `failed`.

O texto bíblico e a citação do payload nunca vêm da LLM: são resolvidos aqui a partir da referência.
"""

import calendar
import datetime as dt
import logging
from dataclasses import dataclass
from pathlib import Path

from blivre import Reference, format_reference, parse_reference
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bible.crossrefs import CrossReferenceRepository
from app.bible.repository import BibleRepository
from app.db.models import CuratedQuote, ReserveStudy, Study
from app.domain.calendar import TZ, special_day_for
from app.domain.content_rules import load_banned, validate_study
from app.domain.quotes import Quote, choose_quote
from app.domain.study import (
    ComplementaryReadingOut,
    QuoteOut,
    SpecialDayOut,
    StudyLlmOutput,
    StudyPayload,
    VerseOut,
    VerseRefOut,
)
from app.domain.verse_plan import NO_REPEAT_DAYS, Choice, choose_verse, load_plan
from app.llm import LlmClient, LlmError
from app.services.content_data import load_active_plan
from app.services.reserve import to_template
from app.services.studies import compute_etag

log = logging.getLogger("app.generation")

PROMPT_VERSION = "study_v1"
PROMPTS = Path(__file__).resolve().parents[2] / "prompts"
MAX_CANDIDATES = 8
CANDIDATE_TEXT_CHARS = 180


def load_prompt(name: str) -> tuple[str, str]:
    text = (PROMPTS / f"{name}.md").read_text()
    text = "\n".join(line for line in text.splitlines() if not line.startswith("<!--"))
    _, rest = text.split("# system", 1)
    system, user = rest.split("# user", 1)
    return system.strip(), user.strip()


@dataclass
class GenerationOutcome:
    date: dt.date
    status: str  # "published" | "failed" | "skipped"
    verse_ref: str
    attempts: int = 0
    error: str | None = None


def _ref_out(ref: Reference) -> VerseRefOut:
    r = ref.ranges[0]
    return VerseRefOut(book=ref.book, chapter=r.chapter, verse_start=r.verse_start, verse_end=r.verse_end)


class GenerationService:
    def __init__(
        self,
        session: AsyncSession,
        bible: BibleRepository,
        crossrefs: CrossReferenceRepository,
        llm: LlmClient,
        *,
        max_tokens: int | None = None,
        clock=lambda: dt.datetime.now(dt.UTC),
    ):
        self.session = session
        self.bible = bible
        self.crossrefs = crossrefs
        self.llm = llm
        self.max_tokens = max_tokens
        self.clock = clock
        self.banned = load_banned()

    # --- dados ----------------------------------------------------------------------------------

    async def _verse_history(self, before: dt.date) -> list[tuple[dt.date, str]]:
        rows = await self.session.execute(
            select(Study.date, Study.verse_ref).where(Study.date < before, Study.status == "published")
        )
        return [(d, r) for d, r in rows]

    async def _quotes(self, before: dt.date) -> tuple[list[Quote], dict[str, CuratedQuote], list]:
        rows = (await self.session.scalars(select(CuratedQuote).where(CuratedQuote.active))).all()
        by_code = {r.code: r for r in rows}
        quotes = [Quote(r.code, tuple(r.tags or ()), r.author, r.source or "", "", "", r.text) for r in rows]
        hist = await self.session.execute(
            select(Study.date, CuratedQuote.code)
            .join(CuratedQuote, Study.quote_id == CuratedQuote.id)
            .where(Study.date < before, Study.status == "published")
        )
        return quotes, by_code, [(d, c) for d, c in hist]

    async def _plan(self):
        return await load_active_plan(self.session) or load_plan()

    # --- prompt ---------------------------------------------------------------------------------

    def build_prompt(
        self, date: dt.date | None, choice: Choice, base_text: str, candidates: list[Reference]
    ) -> tuple[str, str]:
        """`date=None` = estudo de reserva (sem data, sem data especial)."""
        system, user_t = load_prompt(PROMPT_VERSION)
        sd = special_day_for(date) if date else None
        lines = []
        for i, c in enumerate(candidates):
            text = self.bible.get_text(c)
            if len(text) > CANDIDATE_TEXT_CHARS:
                text = text[:CANDIDATE_TEXT_CHARS].rsplit(" ", 1)[0] + "…"
            lines.append(f"{i}. {format_reference(c)} — {text}")
        user = user_t.format(
            data=date.isoformat()
            if date
            else "sem data fixa (estudo de reserva; não cite datas nem estações)",
            dia_especial=f"Data especial: {sd.name_pt}" if sd else "Dia comum (sem data especial)",
            tema=choice.theme or "livre",
            referencia=format_reference(parse_reference(choice.ref)),
            texto=base_text,
            candidatos="\n".join(lines),
        )
        return system, user

    # --- geração --------------------------------------------------------------------------------

    async def _produce(self, date: dt.date | None, choice: Choice, quote_date: dt.date) -> "_Produced":
        """Chama a LLM e monta o payload (para `date`, ou sem data se reserva). Não grava nada."""
        base_ref = parse_reference(choice.ref)
        passage = self.bible.get_passage(base_ref)
        candidates = self.crossrefs.candidates(base_ref, limit=MAX_CANDIDATES)
        quotes, quote_rows, quote_hist = await self._quotes(quote_date)
        quote = choose_quote(quote_date, [choice.theme], quotes, quote_hist)
        quote_id = quote_rows[quote.id].id if quote else None
        if not candidates:
            return _Produced(None, quote_id, 0, "sem candidatos de leitura complementar")
        system, user = self.build_prompt(date, choice, passage.text, candidates)

        def rules(out: StudyLlmOutput) -> list[str]:
            return validate_study(
                out, n_candidates=len(candidates), base_text=passage.text, ref_exists=self.bible.exists,
                banned=self.banned,
            )  # fmt: skip

        # encerra a transação de leitura antes da LLM (pode levar minutos): não segura locks/conexão
        await self.session.commit()
        try:
            result = await self.llm.generate_json(
                system=system, user=user, schema=StudyLlmOutput, max_tokens=self.max_tokens, validate=rules
            )
        except LlmError as exc:
            detail = getattr(exc, "last_error", None)
            error = f"{type(exc).__name__}: {exc}" + (f" | último erro: {detail}" if detail else "")
            return _Produced(None, quote_id, getattr(exc, "attempts", 0), error)

        out = result.data
        chosen = candidates[out.complementary_reading.candidate_index]
        sd = special_day_for(date) if date and choice.special_day else None
        ref_date = date or quote_date
        payload = StudyPayload(
            date=ref_date.isoformat(),
            day_of_year=ref_date.timetuple().tm_yday,
            days_in_year=366 if calendar.isleap(ref_date.year) else 365,
            special_day=SpecialDayOut(key=sd.key, name=sd.name_pt) if sd else None,
            title=out.title.upper(),
            verse=VerseOut(ref=_ref_out(base_ref), display_ref=format_reference(base_ref), text=passage.text),
            body=out.body,
            application=out.application,
            prayer=out.prayer,
            quote=QuoteOut(id=quote.id, text=quote.text, author=quote.author, source="curated")
            if quote
            else None,
            complementary_reading=ComplementaryReadingOut(
                ref=_ref_out(chosen),
                display_ref=format_reference(chosen),
                reason=out.complementary_reading.reason,
            ),
            keywords=out.keywords,
            generated_at=self.clock().isoformat().replace("+00:00", "Z"),
        ).model_dump(mode="json")
        log.info(
            "estudo gerado",
            extra={"date": ref_date.isoformat(), "attempt": result.attempts, "provider": result.provider,
                   "model": result.model, "prompt_version": PROMPT_VERSION},
        )  # fmt: skip
        return _Produced(payload, quote_id, result.attempts, None)

    async def generate(self, date: dt.date, force: bool = False) -> GenerationOutcome:
        existing = await self.session.get(Study, date)
        if existing is not None and existing.status == "published" and not force:
            return GenerationOutcome(date, "skipped", existing.verse_ref)

        choice = choose_verse(date, await self._plan(), await self._verse_history(date))
        produced = await self._produce(date, choice, date)

        study = existing or Study(date=date, verse_ref=choice.ref)
        if existing is None:
            self.session.add(study)
        study.verse_ref = choice.ref
        study.special_day = choice.special_day
        study.prompt_version = PROMPT_VERSION
        study.provider, study.model = self.llm.provider, self.llm.model
        study.quote_id = produced.quote_id
        if produced.payload is None:
            return await self._fail(study, produced.error or "falha", produced.attempts)
        now = self.clock()
        study.payload = produced.payload
        study.etag = compute_etag(produced.payload)
        study.status = "published"  # DECISOES L8: publicação automática após as validações
        study.generated_at = study.published_at = now
        study.is_fallback = False
        await self.session.commit()
        return GenerationOutcome(date, "published", choice.ref, produced.attempts)

    async def _reserve_choice(self) -> Choice:
        """Versículo comum fora dos últimos 365 dias, fora de outras reservas e longe no rodízio."""
        today = self.clock().astimezone(TZ).date()
        plan = [e for e in await self._plan() if e.special_day is None]
        history = await self._verse_history(today + dt.timedelta(days=1))
        recent = {r for d, r in history if (today - d).days <= NO_REPEAT_DAYS}
        reserved = set(
            await self.session.scalars(select(ReserveStudy.verse_ref).where(ReserveStudy.used_on.is_(None)))
        )
        index = {e.ref: i for i, e in enumerate(plan)}
        last = next((index[r] for _, r in sorted(history, reverse=True) if r in index), -1)
        start = last + len(plan) // 2  # metade do rodízio à frente: não vai coincidir tão cedo
        for step in range(len(plan)):
            e = plan[(start + step) % len(plan)]
            if e.ref not in recent and e.ref not in reserved:
                return Choice(e.ref, None, e.theme)
        raise RuntimeError("nenhum versículo disponível para reserva")

    async def generate_reserve(self) -> GenerationOutcome:
        today = self.clock().astimezone(TZ).date()
        choice = await self._reserve_choice()
        produced = await self._produce(None, choice, today)
        if produced.payload is None:
            log.warning("reserva falhou", extra={"error_type": (produced.error or "").split(":")[0]})
            return GenerationOutcome(today, "failed", choice.ref, produced.attempts, produced.error)
        self.session.add(
            ReserveStudy(
                verse_ref=choice.ref, quote_id=produced.quote_id, payload=to_template(produced.payload),
                provider=self.llm.provider, model=self.llm.model, prompt_version=PROMPT_VERSION,
            )
        )  # fmt: skip
        await self.session.commit()
        return GenerationOutcome(today, "published", choice.ref, produced.attempts)

    async def _fail(self, study: Study, error: str, attempts: int) -> GenerationOutcome:
        study.status = "failed"
        study.payload = None
        study.etag = None
        await self.session.commit()
        log.warning(
            "geração falhou", extra={"date": study.date.isoformat(), "error_type": error.split(":")[0]}
        )
        return GenerationOutcome(study.date, "failed", study.verse_ref, attempts, error)


@dataclass
class _Produced:
    payload: dict | None
    quote_id: int | None
    attempts: int
    error: str | None
