"""Healthcheck do contêiner `worker`: saudável se o heartbeat foi atualizado recentemente."""

import sys
import tempfile
import time
from pathlib import Path

HEARTBEAT = Path(tempfile.gettempdir()) / "mana-worker-heartbeat"
INTERVAL_S = 30


def is_healthy(now: float | None = None, max_age_s: float = INTERVAL_S * 4) -> bool:
    try:
        last = float(HEARTBEAT.read_text())
    except (OSError, ValueError):
        return False
    return ((now or time.time()) - last) < max_age_s


if __name__ == "__main__":
    sys.exit(0 if is_healthy() else 1)
