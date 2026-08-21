# Developer and E2E readiness

This file is an operational checklist, not a historical pass report. It keeps
all commands repository-local and points to the canonical quality contract.

## Required local gates

```powershell
# Hermetic harness and quality inventory
python verify_harness.py --repo-only
python scripts/quality/check_orphans_and_anti_patterns.py

# Backend
uv run pytest -q

# Frontend static checks, tests, and production build
npm run typecheck --prefix frontend
npm run lint --prefix frontend
npm run test --prefix frontend -- --silent=true
npm run build --prefix frontend

# Browser matrix (requires the application services)
npm exec --prefix frontend playwright test
```

The canonical thresholds and supported report formats live in
[`quality/quality-contract.json`](quality/quality-contract.json) and
[`TESTING.md`](TESTING.md). CI additionally runs Go/Rust race and mutation
gates, dependency/security scans, Helm/Kubernetes contracts, and the full
Playwright matrix.

## Environment-dependent checks

Run infrastructure-backed checks only when their services are available. A
missing optional service must be reported as an explicit environment skip; it
must not be converted into a fabricated pass. For MCP setup and recipes see
[`docs/mcp/MCP_RECIPES.md`](docs/mcp/MCP_RECIPES.md).
