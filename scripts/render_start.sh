#!/bin/sh
set -e

echo "Running database migrations..."
alembic upgrade head

if [ "${RUN_BOOTSTRAP:-false}" = "true" ]; then
  echo "Bootstrapping super_admin..."
  python scripts/bootstrap_super_admin.py
fi

PORT="${PORT:-8000}"
echo "Starting uvicorn on 0.0.0.0:${PORT}"
exec uvicorn main:app --host 0.0.0.0 --port "${PORT}"
