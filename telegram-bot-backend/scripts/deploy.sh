#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
  echo ".env file is missing in $ROOT_DIR" >&2
  exit 1
fi

echo "Building images..."
docker compose build api bot worker beat init-db

echo "Starting database and Redis..."
docker compose up -d db redis

echo "Waiting for PostgreSQL..."
for _ in $(seq 1 60); do
  if docker compose exec -T db pg_isready -U bot_user -d bot_db >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

if ! docker compose exec -T db pg_isready -U bot_user -d bot_db >/dev/null 2>&1; then
  echo "PostgreSQL did not become ready in time" >&2
  exit 1
fi

echo "Waiting for Redis..."
for _ in $(seq 1 60); do
  if docker compose exec -T redis redis-cli ping >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

if ! docker compose exec -T redis redis-cli ping >/dev/null 2>&1; then
  echo "Redis did not become ready in time" >&2
  exit 1
fi

echo "Applying Alembic migrations..."
docker compose run --rm --no-deps api alembic upgrade head

echo "Running legacy data migration..."
docker compose run --rm --no-deps api python /app/scripts/migrate_to_json_config.py

echo "Seeding initial data..."
docker compose run --rm --no-deps api python -m app.db.seed

echo "Starting application services..."
docker compose up -d --no-deps api bot worker beat

docker compose ps
