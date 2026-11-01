"""Processo do worker: `python -m worker`.

Por enquanto só mantém o heartbeat do healthcheck. O agendador de geração entra na tarefa 3.8.
"""

import logging
import signal
import threading
import time

from worker.healthcheck import HEARTBEAT, INTERVAL_S

log = logging.getLogger("worker")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    log.info("worker iniciado (agendador ainda não implementado — tarefa 3.8)")
    while not stop.is_set():
        HEARTBEAT.write_text(str(time.time()))
        stop.wait(INTERVAL_S)
    log.info("worker encerrado")


if __name__ == "__main__":
    main()
