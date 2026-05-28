#!/bin/sh
set -e

if [ -n "${DATABASE_URL:-}" ]; then
  python - <<'PY'
import os
from urllib.parse import urlparse

url = os.environ.get("DATABASE_URL", "").replace("postgres://", "postgresql://", 1)
host = urlparse(url).hostname or "n/a"
print(f"Database host: {host}")
if host.startswith("dpg-") and host.endswith("-a") and "." not in host:
    print(
        "WARN: hostname interne Render (dpg-*-a). "
        "L'API et PostgreSQL doivent être dans la MÊME région Render "
        "(ex. frankfurt + frankfurt). Sinon utiliser l'URL EXTERNE de la base."
    )
PY
fi

echo "Running database migrations..."
alembic upgrade head

if [ "${RUN_BOOTSTRAP:-false}" = "true" ]; then
  echo "Bootstrapping super_admin..."
  python scripts/bootstrap_super_admin.py
fi

PORT="${PORT:-8000}"
echo "Starting uvicorn on 0.0.0.0:${PORT}"
exec uvicorn main:app --host 0.0.0.0 --port "${PORT}"
