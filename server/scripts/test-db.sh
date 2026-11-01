#!/usr/bin/env bash
# Sobe/derruba um PostgreSQL 16 descartável para os testes de banco (porta 127.0.0.1:55432).
#   scripts/test-db.sh up   → depois: export TEST_DATABASE_URL=postgresql+psycopg://mana:mana@127.0.0.1:55432/mana_test
#   scripts/test-db.sh down
set -euo pipefail
PODMAN=(podman)
if command -v distrobox-host-exec >/dev/null && [ -n "${CONTAINER_ID:-}${DISTROBOX_ENTER_PATH:-}" ]; then
  PODMAN=(distrobox-host-exec podman)
fi
NAME=mana-test-db
case "${1:-up}" in
  up)
    "${PODMAN[@]}" rm -f "$NAME" >/dev/null 2>&1 || true
    "${PODMAN[@]}" run -d --name "$NAME" -p 127.0.0.1:55432:5432 \
      -e POSTGRES_USER=mana -e POSTGRES_PASSWORD=mana -e POSTGRES_DB=mana_test \
      --tmpfs /var/lib/postgresql/data docker.io/library/postgres:16-alpine >/dev/null
    for _ in $(seq 1 30); do
      if "${PODMAN[@]}" exec "$NAME" pg_isready -U mana -d mana_test >/dev/null 2>&1; then
        echo "TEST_DATABASE_URL=postgresql+psycopg://mana:mana@127.0.0.1:55432/mana_test"; exit 0
      fi
      sleep 1
    done
    echo "PostgreSQL não ficou pronto" >&2; exit 1 ;;
  down) "${PODMAN[@]}" rm -f "$NAME" >/dev/null ;;
  *) echo "uso: $0 up|down" >&2; exit 2 ;;
esac
