SHELL := /bin/bash
export UV_CACHE_DIR := $(CURDIR)/.local/cache/uv
export npm_config_cache := $(CURDIR)/.local/cache/npm
PY := .venv/bin/python
UV := uv
COMPOSE := docker compose

.PHONY: bootstrap lint test test-python test-e2e test-security up down migrate seed-demo fixtures contract dev-api dev-web benchmark backup restore-check

bootstrap:
	$(UV) sync --frozen --extra ai
	npm --prefix apps/web ci
	$(PY) scripts/bootstrap.py

lint:
	.venv/bin/ruff check apps/api packages scripts tests migrations
	.venv/bin/ruff format --check apps/api packages scripts tests migrations
	.venv/bin/mypy
	npm --prefix apps/web run lint
	$(PY) scripts/export_openapi.py --check

test: test-python
	npm --prefix apps/web test

test-python:
	.venv/bin/pytest

test-e2e:
	npm --prefix apps/web run test:e2e

test-security:
	.venv/bin/pytest tests/security -q
	.venv/bin/bandit -q -r apps/api packages

up:
	$(COMPOSE) up -d --build --wait

down:
	$(COMPOSE) down

migrate:
	$(COMPOSE) run --rm migrate

seed-demo:
	$(COMPOSE) exec api python -m wdh_api.seed

fixtures:
	$(PY) scripts/generate_fixtures.py --output .local/fixtures-$$(date -u +%Y%m%dT%H%M%S)-$${RANDOM}

contract:
	$(PY) scripts/export_openapi.py

dev-api:
	.venv/bin/uvicorn wdh_api.main:create_app --factory --host 127.0.0.1 --port 8000

dev-web:
	npm --prefix apps/web run dev

backup:
	$(COMPOSE) exec api python -m wdh_api.cli backup

restore-check:
	.venv/bin/pytest tests/integration/test_backup.py -q

benchmark:
	$(PY) scripts/benchmark.py

worker:
	.venv/bin/python -m wdh_api.worker

# Explicit downloads of pinned public assets; startup never downloads weights.
models:
	$(PY) -m wdh_api.models install ocr --root .local/models
	$(PY) -m wdh_api.models install asr --root .local/models
	$(PY) -m wdh_api.models install runtime --root .local/models
	$(PY) -m wdh_api.models install embedding --root .local/models
	$(PY) -m wdh_api.models install llm --root .local/models
