"""Limite de requisições (docs/API.md "Rate limits"). Janela fixa, em memória, por processo.

Basta enquanto houver **uma** réplica da API (o compose sobe uma). Com mais réplicas, trocar o
armazenamento por Postgres/Redis mantendo a mesma interface.
O IP do cliente só é usado como chave em memória (nunca logado nem gravado).
"""

import hashlib
import math
import time
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends, Request

from app.core.errors import ApiError


@dataclass(frozen=True)
class Rule:
    scope: str
    limit: int
    window_s: int


AUTH = Rule("auth", 10, 60)  # por IP
STUDIES = Rule("studies", 60, 60)  # por usuário
PERSONAL = Rule("personal", 20, 3600)  # por usuário
NOTES = Rule("notes", 120, 60)  # por usuário


class RateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic, max_keys: int = 50_000):
        self._clock = clock
        self._max_keys = max_keys
        self._buckets: dict[tuple[str, str], tuple[float, int]] = {}
        self.enabled = True

    def hit(self, rule: Rule, key: str) -> float | None:
        """Registra uma requisição. Devolve None se permitida, ou os segundos até liberar."""
        if not self.enabled:
            return None
        now = self._clock()
        k = (rule.scope, key)
        start, count = self._buckets.get(k, (now, 0))
        if now - start >= rule.window_s:
            start, count = now, 0
        if count >= rule.limit:
            return rule.window_s - (now - start)
        self._buckets[k] = (start, count + 1)
        if len(self._buckets) > self._max_keys:
            self._prune(now)
        return None

    def _prune(self, now: float) -> None:
        longest = max((r.window_s for r in (AUTH, STUDIES, PERSONAL, NOTES)), default=3600)
        self._buckets = {k: v for k, v in self._buckets.items() if now - v[0] < longest}


def get_limiter(request: Request) -> RateLimiter:
    limiter = getattr(request.app.state, "limiter", None)
    if limiter is None:
        limiter = request.app.state.limiter = RateLimiter()
    return limiter


def _raise(retry_after: float) -> None:
    seconds = max(1, math.ceil(retry_after))
    raise ApiError(
        "rate_limited",
        "Muitas requisições. Tente novamente em instantes.",
        429,
        {"retry_after_seconds": seconds},
        headers={"Retry-After": str(seconds)},
    )


def _ip_key(request: Request) -> str:
    ip = request.client.host if request.client else "desconhecido"
    return hashlib.sha256(ip.encode()).hexdigest()[:16]


def limit_by_ip(rule: Rule):
    def dep(request: Request, limiter: RateLimiter = Depends(get_limiter)) -> None:
        if (wait := limiter.hit(rule, _ip_key(request))) is not None:
            _raise(wait)

    return dep


def limit_by_user(rule: Rule):
    from app.api.deps import get_current_user
    from app.db.models import User

    def dep(user: User = Depends(get_current_user), limiter: RateLimiter = Depends(get_limiter)) -> None:
        if (wait := limiter.hit(rule, str(user.id))) is not None:
            _raise(wait)

    return dep
