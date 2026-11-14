.PHONY: install dev dev-api web test lint format backend-test backend-lint web-test web-lint

install:
	cd backend && uv sync
	cd web && pnpm install --frozen-lockfile

dev:
	$(MAKE) -j2 dev-api web

dev-api:
	cd backend && uv run firecal serve --reload

test: backend-test web-test

lint: backend-lint web-lint

backend-test:
	cd backend && uv run pytest

backend-lint:
	cd backend && uv run ruff check . && uv run ruff format --check .

format:
	cd backend && uv run ruff check --fix . && uv run ruff format .

web:
	cd web && pnpm dev

web-test:
	cd web && pnpm test

web-lint:
	cd web && pnpm typecheck && pnpm lint
