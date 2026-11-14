.PHONY: install dev dev-api web test lint format backend-test backend-lint web-test web-lint

install:
	cd backend && uv sync

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

# Placeholders: the web session replaces these three targets when web/ lands.
web:
	@echo "web/: placeholder, owned by the web session (SA0.4/SA0.5)"

web-test:
	@echo "web/: placeholder, owned by the web session (SA0.4/SA0.5)"

web-lint:
	@echo "web/: placeholder, owned by the web session (SA0.4/SA0.5)"
