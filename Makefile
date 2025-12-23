ROOT_DIR := $(CURDIR)/root
FRONTEND_DIR := $(ROOT_DIR)/frontend
ENV_FILE ?= $(ROOT_DIR)/.env

.PHONY: install backend-install frontend-install lint lint-backend lint-frontend backend-test frontend-test test backend-typecheck frontend-typecheck frontend-build frontend-dev backend-serve generate-api alembic-check compose-lint docker-build docker-up docker-down coverage test-quick clean

install: backend-install frontend-install

backend-install:
	python -m pip install --upgrade pip
	python -m pip install -r $(ROOT_DIR)/requirements.txt -r $(ROOT_DIR)/requirements-dev.txt

frontend-install:
	npm ci --prefix $(FRONTEND_DIR)

lint: lint-backend lint-frontend

compose-lint:
	docker compose -f $(CURDIR)/docker-compose.yml config

lint-backend:
	pre-commit run --all-files

lint-frontend:
	npm run lint --prefix $(FRONTEND_DIR)
	npm run manifests:check --prefix $(FRONTEND_DIR)
	npm run format:check --prefix $(FRONTEND_DIR)

backend-test:
cd $(ROOT_DIR) && pytest --cov=app --cov-report=xml --cov-report=term-missing --cov-fail-under=85 --junitxml=pytest-report.xml

backend-typecheck:
	cd $(ROOT_DIR) && mypy

frontend-test:
	npm run typecheck --prefix $(FRONTEND_DIR)
	npm run test:ci --prefix $(FRONTEND_DIR)

frontend-build:
	npm run build --prefix $(FRONTEND_DIR)

frontend-dev:
	npm run dev --prefix $(FRONTEND_DIR) -- --host 0.0.0.0 --port 5173

backend-serve:
	cd $(ROOT_DIR) && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --env-file $(ENV_FILE)

test: backend-test frontend-test

# Quick test without coverage (faster)
test-quick:
	cd $(ROOT_DIR) && pytest -x -q

# Coverage report with HTML output
coverage:
	cd $(ROOT_DIR) && pytest --cov=app --cov-report=html --cov-report=term
	@echo "Coverage report: $(ROOT_DIR)/htmlcov/index.html"

alembic-check:
	cd $(ROOT_DIR) && DATABASE_URL=sqlite+aiosqlite:///./ci-migrations.db alembic -c alembic.ini upgrade head && \
		DATABASE_URL=sqlite+aiosqlite:///./ci-migrations.db alembic -c alembic.ini downgrade base

generate-api:
		cd $(ROOT_DIR) && python3 - <<'PY'
	import json
	import pathlib
	from app.main import app

	schema_path = pathlib.Path("frontend/openapi.json")
	schema_path.write_text(json.dumps(app.openapi()))
	PY
	npm run generate:api --prefix $(FRONTEND_DIR)
	rm -f $(ROOT_DIR)/frontend/openapi.json

# Docker commands
docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

# Cleanup artifacts
clean:
	find $(ROOT_DIR) -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find $(ROOT_DIR) -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find $(ROOT_DIR) -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find $(ROOT_DIR) -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf $(ROOT_DIR)/htmlcov $(ROOT_DIR)/.coverage $(ROOT_DIR)/coverage.xml
	rm -rf $(FRONTEND_DIR)/dist $(FRONTEND_DIR)/node_modules/.cache

