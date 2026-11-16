.PHONY: install dev dev-api web test lint format backend-test backend-lint web-test web-lint data static-export static-site

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

# Frozen calibration applied by `make data` (committed in backend/calibrations/; never re-fitted here).
CALIBRATION ?= sf-2026.11.2

# Full data pipeline (FIRMS, NOAA CPC ONI, harmonized series). Heavy: see README for the memory cap.
# Months after the per-country files (2026 on) come from the FIRMS area API and need FIRMS_MAP_KEY; without it
# the series ends with the per-country files. nrt-mask and completeness read detections, so they run before grid.
data:
	cd backend && uv run firecal enso build && uv run firecal firms download && uv run firecal firms ingest
	@if [ -n "$$FIRMS_MAP_KEY" ]; then \
		cd backend && uv run firecal boundaries fetch && uv run firecal firms area && uv run firecal firms area-ingest \
			&& uv run firecal firms nrt-mask && uv run firecal firms completeness; \
	else echo "FIRMS_MAP_KEY not set: area API skipped, the series ends with the per-country files"; fi
	cd backend && uv run firecal firms grid && uv run firecal series build --version $(CALIBRATION)

# Static export per province and department (SA7.2), into data/publish/static.
static-export:
	cd backend && uv run firecal boundaries fetch && uv run firecal publish export --workers $${WORKERS:-2}

# Deployable site in data/publish/site (must not exist yet): web build with VITE_DATA_URL=/data plus the export.
static-site:
	cd web && pnpm build:static
	mkdir data/publish/site
	cd web/dist && find . -mindepth 1 -maxdepth 1 ! -name static-e2e -exec cp -r {} ../../data/publish/site/ \;
	cp -r data/publish/static data/publish/site/data

web-test:
	cd web && pnpm test

web-lint:
	cd web && pnpm typecheck && pnpm lint
