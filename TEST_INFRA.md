# E2E Test Infra: university_ecosystem MCP Configuration

## Test Philosophy
Opaque-box and requirement-driven configuration validation for MCP servers and Antigravity permission policies.

## Validation Tiers
- **Tier 1: Syntax & Parse Validation**: JSON parsing without syntax errors for `mcp_config.json` and `config.json`.
- **Tier 2: Server Definition & Schema Validation**:
  - Redis: Port 63791, `npx -y @modelcontextprotocol/server-redis@latest`, `REDIS_URL` env.
  - MinIO/S3: Endpoint `http://127.0.0.1:9000`, `npx -y mcp-server-s3@latest`, S3 protocol compatibility env vars (`AWS_ENDPOINT_URL`, `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_FORCE_PATH_STYLE`).
  - Elasticsearch: Endpoint `http://127.0.0.1:9200`, `npx -y @elastic/mcp-server-elasticsearch@latest`, `ES_URL` / `ELASTICSEARCH_URL` env.
  - GitHub: `npx -y @modelcontextprotocol/server-github@latest`, `GITHUB_PERSONAL_ACCESS_TOKEN` env mapping.
  - Playwright: `npx -y @executeautomation/playwright-mcp-server@latest`.
  - Docker: `npx -y mcp-server-docker@latest` (preserved).
  - Existing servers preserved (`chrome-devtools-mcp`, `context7`, `gopls-mcp-server`, `kubernetes`, `memory`, `postgres`, `sequential-thinking`).
- **Tier 3: Permission Grants Coverage**:
  - `userSettings.globalPermissionGrants.allow` contains wildcard grants or complete tool grants covering `docker`, `redis`, `minio`/`s3`, `elasticsearch`, `github`, `playwright`.
  - Existing permission grants preserved.
- **Tier 4: Non-Destructive Integrity**:
  - Other user settings in `config.json` (themes, policies, plugins) remain intact.
