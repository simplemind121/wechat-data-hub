SHELL := /bin/bash
export UV_CACHE_DIR := $(CURDIR)/.local/cache/uv
export npm_config_cache := $(CURDIR)/.local/cache/npm
PY := .venv/bin/python
UV := uv
COMPOSE := docker compose

.PHONY: bootstrap lint test test-python test-e2e test-security up down migrate seed-demo fixtures contract dev-api dev-web benchmark backup restore-check

bootstrap:
	$(UV) sync --frozen
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

seed-demo: fixtures
	@echo "Synthetic files generated. Database import is not implemented (WDH-014); no records were seeded."
	@exit 2

fixtures:
	$(PY) scripts/generate_fixtures.py --output .local/fixtures-$$(date -u +%Y%m%dT%H%M%S)-$${RANDOM}

contract:
	$(PY) scripts/export_openapi.py

dev-api:
	.venv/bin/uvicorn wdh_api.main:create_app --factory --host 127.0.0.1 --port 8000

dev-web:
	npm --prefix apps/web run dev

benchmark backup restore-check:
	@echo "BLOCKED: $@ is not implemented. See TASKS.md (WDH-061/062)."
	@exit 2
