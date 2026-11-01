"""Caso de uso do `/v1/health`: agrega verificações de dependências."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

Check = Callable[[], Awaitable[str]]


@dataclass
class HealthReport:
    status: str  # "ok" | "error"
    db: str  # "ok" | "error" | "not_configured"
    llm: str  # "ok" | "degraded"
    today_published: bool

    @property
    def healthy(self) -> bool:
        return self.status == "ok"


class HealthService:
    def __init__(self, db_check: Check, llm_check: Check, today_published: Callable[[], Awaitable[bool]]):
        self._db = db_check
        self._llm = llm_check
        self._today = today_published

    async def report(self) -> HealthReport:
        db, llm = await asyncio.gather(self._db(), self._llm())
        today = await self._today() if db == "ok" else False
        # LLM fora do ar não derruba a API (o app usa estudos já gerados); banco fora derruba.
        status = "ok" if db in ("ok", "not_configured") else "error"
        return HealthReport(status=status, db=db, llm=llm, today_published=today)
