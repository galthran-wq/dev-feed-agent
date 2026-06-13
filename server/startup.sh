#!/bin/bash
set -e

echo "Running database migrations..."
alembic upgrade head
echo "Migrations completed!"
echo "Starting server..."
exec uvicorn src.main:app --host 0.0.0.0 --port 8000
