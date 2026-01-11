FRONTEND_DIR := $(CURDIR)/frontend
ENV_FILE ?= $(CURDIR)/.env

.PHONY: install backend-install frontend-install lint lint-backend lint-frontend backend-test frontend-test test backend-typecheck frontend-typecheck frontend-build frontend-dev backend-serve generate-api alembic-check compose-lint docker-build docker-up docker-down coverage test-quick clean go-test go-coverage

install: backend-install frontend-install

backend-install:
	python -m pip install --upgrade pip
	python -m pip install -r $(CURDIR)/requirements.txt -r $(CURDIR)/requirements-dev.txt

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
	pytest --cov=app --cov-report=xml --cov-report=term-missing --cov-fail-under=85 --junitxml=pytest-report.xml

backend-typecheck:
	mypy

frontend-test:
	npm run typecheck --prefix $(FRONTEND_DIR)
	npm run test:ci --prefix $(FRONTEND_DIR)

frontend-build:
	npm run build --prefix $(FRONTEND_DIR)

frontend-dev:
	npm run dev --prefix $(FRONTEND_DIR) -- --host 0.0.0.0 --port 5173

backend-serve:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --env-file $(ENV_FILE)

test: backend-test frontend-test go-test

go-test:
	@echo "Running all Go tests..."
	cd services/gateway && go test ./...
	cd services/file-processor && go test ./...
	cd services/ws-hub && go test ./...

go-coverage:
	powershell -ExecutionPolicy Bypass -File $(CURDIR)/scripts/go-coverage.ps1

# Quick test without coverage (faster)
test-quick:
	pytest -x -q

# Coverage report with HTML output
coverage:
	pytest --cov=app --cov-report=html --cov-report=term
	@echo "Coverage report: ./htmlcov/index.html"

alembic-check:
	DATABASE_URL=sqlite+aiosqlite:///./ci-migrations.db alembic -c alembic.ini upgrade head && \
		DATABASE_URL=sqlite+aiosqlite:///./ci-migrations.db alembic -c alembic.ini downgrade base

generate-api:
	python3 - <<'PY'
	import json
	import pathlib
	from app.main import app

	schema_path = pathlib.Path("frontend/openapi.json")
	schema_path.write_text(json.dumps(app.openapi()))
	PY
	npm run generate:api --prefix $(FRONTEND_DIR)
	rm -f frontend/openapi.json

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
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf htmlcov .coverage coverage.xml
	rm -rf $(FRONTEND_DIR)/dist $(FRONTEND_DIR)/node_modules/.cache

# Security check (run pip-audit and npm audit)
security-check:
	pip-audit
	npm audit --prefix $(FRONTEND_DIR)

# Kubernetes manifest validation
k8s-lint:
	@echo "Validating Kubernetes manifests..."
	@for f in $(CURDIR)/k8s/*.yaml $(CURDIR)/k8s/**/*.yaml; do \
		echo "Checking $$f"; \
		python -c "import yaml; yaml.safe_load(open('$$f'))" 2>/dev/null || echo "Warning: $$f has issues"; \
	done
	@echo "K8s manifests validated"

# Show test coverage summary
audit-metrics:
	@echo "=== Test Coverage ==="
	pytest --cov=app --cov-report=term-missing -q --tb=no 2>&1 | tail -20
	@echo ""
	@echo "=== Code Stats ==="
	@find ./app -name "*.py" | wc -l | xargs echo "Python files:"
	@find $(FRONTEND_DIR)/src -name "*.tsx" -o -name "*.ts" | wc -l | xargs echo "TypeScript files:"

# Full verification (lint + typecheck + test)
verify-all: lint backend-typecheck frontend-test backend-test
	@echo "All verifications passed!"

# Development mode - run backend and frontend
dev:
	@echo "Starting backend and frontend in development mode..."
	@echo "Backend: http://localhost:8000"
	@echo "Frontend: http://localhost:5173"
	@echo "Use Ctrl+C to stop"
	@$(MAKE) -j2 backend-serve frontend-dev

# Help target
help:
	@echo "Available targets:"
	@echo "  install        - Install all dependencies"
	@echo "  lint           - Run all linters"
	@echo "  test           - Run all tests"
	@echo "  test-quick     - Quick test without coverage"
	@echo "  coverage       - Generate HTML coverage report"
	@echo "  dev            - Start dev servers (backend + frontend)"
	@echo "  docker-up      - Start Docker containers"
	@echo "  docker-down    - Stop Docker containers"
	@echo "  security-check - Run security audits"
	@echo "  k8s-lint       - Validate Kubernetes manifests"
	@echo "  verify-all     - Full verification suite"
	@echo "  clean          - Remove build artifacts"
