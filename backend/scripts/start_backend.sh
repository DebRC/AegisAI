#!/bin/sh
set -eu

echo "Running unit tests..."
python -m unittest discover -s tests -v

echo "Applying database migrations..."
alembic upgrade head

echo "Starting AegisAI..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log
