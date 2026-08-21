# University Ecosystem Platform — Master MCP Integration & Recipes Guide

## 1. Executive Overview & Architecture

The Model Context Protocol (MCP) standardizes how autonomous agents and human developers interface with external services, runtimes, persistent storage, and diagnostic tooling. Within the **University Ecosystem Platform**, MCP provides a deterministic, zero-trust verification layer across 14 dedicated servers.

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                               Antigravity Developer Agent                                   │
│                        (Lead Architect, TDD Dev, QA Tester, etc.)                          │
└──────────────┬───────────────────────────────┬───────────────────────────────┬──────────────┘
               │                               │                               │
               ▼                               ▼                               ▼
    ┌──────────────────────┐        ┌──────────────────────┐        ┌──────────────────────┐
    │  Browser & Frontend  │        │   Data & Persistence │        │ Runtime & Governance │
    ├──────────────────────┤        ├──────────────────────┤        ├──────────────────────┤
    │ • playwright         │        │ • postgres (15433)   │        │ • docker             │
    │ • chrome-devtools-mcp│        │ • redis (63791)      │        │ • kubernetes         │
    │                      │        │ • minio / s3 (9000)  │        │ • gopls-mcp-server   │
    │                      │        │ • elasticsearch(9200)│        │ • github             │
    └──────────────────────┘        └──────────────────────┘        │ • memory             │
                                                                    │ • context7           │
                                                                    │ • sequential-thinking│
                                                                    └──────────────────────┘
```

All servers are declared in `~/.gemini/config/mcp_config.json` and authorized through granular wildcard permission grants in `~/.gemini/config/config.json`.

---

## 2. Master MCP Server Catalog (14 Servers)

The following table provides the exhaustive catalog of all 14 configured MCP servers, detailing their transport type, execution command, endpoints, authentication mechanisms, and primary responsibilities within the repository.

| # | Server Name | Transport / Type | Command / Endpoint | Environment & Authentication | Primary Tool Capabilities | Repository Responsibility |
|---|---|---|---|---|---|---|
| 1 | `chrome-devtools-mcp` | stdio (`npx`) | `npx -y chrome-devtools-mcp@latest` | Local Chromium session | `navigate_page`, `click`, `fill_form`, `take_screenshot`, `lighthouse_audit`, `list_console_messages`, `performance_analyze_insight`, `take_heapsnapshot` | Low-level browser diagnostics, Core Web Vitals (LCP, INP, CLS <= 0.05), heap profiling, Lighthouse accessibility & WCAG 2.2 AA scoring. |
| 2 | `context7` | HTTP SSE | `https://mcp.context7.com/mcp` | Header: `CONTEXT7_API_KEY: ${CONTEXT7_API_KEY}` | `resolve-library-id`, `query-docs` | Real-time library and framework API documentation retrieval for FastAPI, SQLAlchemy 2.0, Dishka DI, Valibot, TanStack Router, React 19. |
| 3 | `docker` | stdio (`npx`) | `npx -y mcp-server-docker@latest` | Docker Engine Daemon (`//./pipe/docker_engine` / Unix socket) | `run_command` | Inspect container health, inspect compose cluster topologies (`docker-compose.full.yml`, `docker-compose.observability.yml`), verify live logs. |
| 4 | `elasticsearch` | stdio (`npx`) | `npx -y @elastic/mcp-server-elasticsearch@latest` | `ELASTICSEARCH_URL: http://127.0.0.1:9200`<br>`ELASTIC_PASSWORD: ${ELASTIC_PASSWORD}`<br>`ELASTICSEARCH_USERNAME: elastic` | `list_indices`, `get_mappings`, `search`, `get_shards` | Inspect search indices, verify mappings for full-text search, monitor shard allocations and cluster health status. |
| 5 | `github` | stdio (`npx`) | `npx -y @modelcontextprotocol/server-github@latest` | `GITHUB_PERSONAL_ACCESS_TOKEN: ${GITHUB_PERSONAL_ACCESS_TOKEN}` | `create_issue`, `get_pull_request`, `list_pull_requests`, `create_pull_request_review`, `merge_pull_request`, `search_code`, `get_file_contents` | GitHub workflow automation, automated PR reviews, issue management, branch status inspections. |
| 6 | `gopls-mcp-server` | stdio (`go`) | `go run golang.org/x/tools/gopls@latest mcp` | Go 1.22+ SDK toolchain | `go_diagnostics`, `go_file_context`, `go_package_api`, `go_rename_symbol`, `go_search`, `go_symbol_references`, `go_vulncheck`, `go_workspace` | Go language server protocol diagnostics for microservices (`services/ws-hub`, `services/gateway`, `services/file-processor`). |
| 7 | `kubernetes` | stdio (`npx`) | `npx -y mcp-server-kubernetes@latest` | Local `~/.kube/config` context | `kubectl_get`, `kubectl_describe`, `kubectl_apply`, `kubectl_logs`, `kubectl_scale`, `kubectl_rollout`, `install_helm_chart`, `port_forward` | Kubernetes deployment verification, ingress routing assertions, Kyverno policy validation, Helm chart tests (`charts/university-ecosystem`). |
| 8 | `memory` | stdio (`npx`) | `npx -y @modelcontextprotocol/server-memory@latest` | Local persistent JSON graph storage | `create_entities`, `create_relations`, `add_observations`, `read_graph`, `search_nodes`, `open_nodes`, `delete_entities` | Persistent cross-turn architectural memory, ADR tracking, inter-service dependency graphs, invariant persistence. |
| 9 | `minio` | stdio (`npx`) | `npx -y mcp-server-s3@latest` | `AWS_ENDPOINT_URL: http://127.0.0.1:9000`<br>`AWS_ACCESS_KEY_ID: minioadmin`<br>`AWS_SECRET_ACCESS_KEY: ${AWS_SECRET_ACCESS_KEY}`<br>`AWS_FORCE_PATH_STYLE: true` | `list_buckets`, `list_objects`, `get_object`, `put_object`, `delete_object`, `presigned_url`, `bucket_info` | S3-compatible object storage verification, static asset uploads, profile pictures, PDF exports, presigned URL testing. |
| 10 | `playwright` | stdio (`npx`) | `npx -y @executeautomation/playwright-mcp-server@latest` | Headless Chromium engine | `playwright_navigate`, `playwright_click`, `playwright_fill`, `playwright_screenshot`, `playwright_evaluate`, `playwright_expect_response`, `playwright_assert_response` | End-to-end user journey simulation, form submissions, network interception, automated authentication flow verification. |
| 11 | `postgres` | stdio (`npx`) | `npx -y @modelcontextprotocol/server-postgres@latest postgresql://postgres:postgres@127.0.0.1:15433/university` | Direct TCP connection to Postgres (Port 15433) | `query` | SQL query execution, Alembic migration verification (`alembic_version`), `EXPLAIN (ANALYZE, BUFFERS)` execution plans, RLS verification. |
| 12 | `redis` | stdio (`npx`) | `npx -y @gongrzhe/server-redis-mcp@latest redis://:redispassword@127.0.0.1:63791` | Direct TCP connection to Redis/Valkey (Port 63791) | `get`, `set`, `delete`, `list` | Cache key verification, TTL validation, session revocation inspection (`session:revocations`, `revoked:jti:*`), cache stampede test. |
| 13 | `s3` | stdio (`npx`) | S3/MinIO operations mapped via MCP S3 Server | Compatible with AWS S3 / MinIO backend | Native S3 object APIs via `minio` namespace | S3 bucket permissions, multipart uploads, policy enforcement. |
| 14 | `sequential-thinking`| stdio (`npx`) | `npx -y @modelcontextprotocol/server-sequential-thinking@latest` | Node.js runtime process | `sequentialthinking` | Dynamic, multi-step structured reasoning, hypothesis formulation, alternative branch tracking during complex debugging. |

---

## 3. Configuration & Global Permission Architecture

### 3.1 Server Definition Configuration (`~/.gemini/config/mcp_config.json`)

All MCP servers are configured under the `mcpServers` object in `~/.gemini/config/mcp_config.json`:

```json
{
  "mcpServers": {
    "chrome-devtools-mcp": {
      "command": "npx",
      "args": ["-y", "chrome-devtools-mcp@latest"]
    },
    "context7": {
      "serverUrl": "https://mcp.context7.com/mcp",
      "headers": {
        "CONTEXT7_API_KEY": "${CONTEXT7_API_KEY}"
      }
    },
    "docker": {
      "command": "npx",
      "args": ["-y", "mcp-server-docker@latest"]
    },
    "elasticsearch": {
      "command": "npx",
      "args": ["-y", "@elastic/mcp-server-elasticsearch@latest"],
      "env": {
        "ELASTICSEARCH_URL": "http://127.0.0.1:9200",
        "ES_URL": "http://127.0.0.1:9200",
        "ELASTICSEARCH_USERNAME": "elastic",
        "ELASTIC_PASSWORD": "${ELASTIC_PASSWORD}",
        "ELASTICSEARCH_PASSWORD": "${ELASTICSEARCH_PASSWORD}",
        "OTEL_LOG_LEVEL": "none"
      }
    },
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github@latest"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_PERSONAL_ACCESS_TOKEN}"
      }
    },
    "gopls-mcp-server": {
      "command": "go",
      "args": ["run", "golang.org/x/tools/gopls@latest", "mcp"]
    },
    "kubernetes": {
      "command": "npx",
      "args": ["-y", "mcp-server-kubernetes@latest"]
    },
    "memory": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-memory@latest"]
    },
    "minio": {
      "command": "npx",
      "args": ["-y", "mcp-server-s3@latest"],
      "env": {
        "AWS_ACCESS_KEY_ID": "minioadmin",
        "AWS_SECRET_ACCESS_KEY": "${AWS_SECRET_ACCESS_KEY}",
        "AWS_ENDPOINT_URL": "http://127.0.0.1:9000",
        "AWS_ENDPOINT_URL_S3": "http://127.0.0.1:9000",
        "AWS_FORCE_PATH_STYLE": "true",
        "AWS_REGION": "us-east-1",
        "AWS_S3_FORCE_PATH_STYLE": "true",
        "S3_ENDPOINT": "http://127.0.0.1:9000"
      }
    },
    "playwright": {
      "command": "npx",
      "args": ["-y", "@executeautomation/playwright-mcp-server@latest"]
    },
    "postgres": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-postgres@latest",
        "postgresql://postgres:b40KLcq32590sP9yUMsDmLRF3lGG6w3t@127.0.0.1:15433/university"
      ]
    },
    "redis": {
      "command": "npx",
      "args": [
        "-y",
        "@gongrzhe/server-redis-mcp@latest",
        "redis://:nViPWOrh7FhdYOE2gdhFBjJa@127.0.0.1:63791"
      ]
    },
    "sequential-thinking": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-sequential-thinking@latest"]
    }
  }
}
```

### 3.2 Global Permission Grants (`~/.gemini/config/config.json`)

To enable seamless autonomous subagent execution without blocking prompts, wildcard permission grants are configured under `userSettings.globalPermissionGrants.allow`:

```json
{
  "userSettings": {
    "globalPermissionGrants": {
      "allow": [
        "mcp(chrome-devtools-mcp/*)",
        "mcp(context7/*)",
        "mcp(docker/*)",
        "mcp(elasticsearch/*)",
        "mcp(github/*)",
        "mcp(gopls-mcp-server/*)",
        "mcp(kubernetes/*)",
        "mcp(memory/*)",
        "mcp(minio/*)",
        "mcp(playwright/*)",
        "mcp(postgres/*)",
        "mcp(redis/*)",
        "mcp(s3/*)",
        "mcp(sequential-thinking/*)"
      ]
    }
  }
}
```

---

## 4. MCP Tool Invocation Mechanics

Antigravity supports two discovery and execution models for MCP tools:

### 4.1 Schema Discovery via Local Directory Inspection
Every registered MCP server exposes its tool definitions as JSON schemas under:
`C:\Users\egorribun\.gemini\antigravity\mcp\<serverName>\<toolName>.json`

When an agent needs to understand the exact parameters of a tool, it inspects the schema file or queries the server directly.

### 4.2 Lazy-Loaded Invocations via `call_mcp_tool`
For lazily loaded tools, the agent invokes `call_mcp_tool` with explicit arguments:

```json
{
  "ServerName": "postgres",
  "ToolName": "query",
  "Arguments": {
    "sql": "SELECT version_num FROM alembic_version LIMIT 1;"
  },
  "toolAction": "Query database",
  "toolSummary": "Verify Alembic version"
}
```

---

## 5. Standardized Troubleshooting & Operational Gotchas

### 5.1 Connection Failures & Port Mapping Table
If an MCP tool returns `ECONNREFUSED` or timeout errors, verify that local services are running and bound to the required host ports:

| Service | Container Internal Port | Host Port | Verification Command (PowerShell) |
|---|---|---|---|
| PostgreSQL | `5432` | `15433` | `Test-NetConnection -ComputerName 127.0.0.1 -Port 15433` |
| Redis / Valkey | `6379` | `63791` | `Test-NetConnection -ComputerName 127.0.0.1 -Port 63791` |
| MinIO (S3 API) | `9000` | `9000` | `Test-NetConnection -ComputerName 127.0.0.1 -Port 9000` |
| MinIO Console | `9001` | `9001` | `Test-NetConnection -ComputerName 127.0.0.1 -Port 9001` |
| Elasticsearch | `9200` | `9200` | `Test-NetConnection -ComputerName 127.0.0.1 -Port 9200` |
| Vite / SSR Frontend | `3000` | `3000` | `Test-NetConnection -ComputerName 127.0.0.1 -Port 3000` |
| Go API Gateway | `8080` | `8080` | `Test-NetConnection -ComputerName 127.0.0.1 -Port 8080` |
| Caddy Reverse Proxy | `80` | `80` | `Test-NetConnection -ComputerName 127.0.0.1 -Port 80` |

To spin up all required dependencies in one step:
```pwsh
pwsh scripts/dc.ps1 -f docker-compose.full.yml up -d
```

### 5.2 Node.js & `npx` Process Management on Windows
- `npx -y <pkg>@latest` downloads and caches packages in `%LOCALAPPDATA%\npm-cache\_npx`.
- In case of lock errors, clear stale locks or terminate dangling `node.exe` worker processes.
- Ensure PowerShell execution policy allows local scripts (`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`).

### 5.3 Token & Secret Hygiene
- Sensitive secrets in `mcp_config.json` (such as `GITHUB_PERSONAL_ACCESS_TOKEN`) should use environment variable substitution `${VAR_NAME}` where possible.
- Never commit `~/.gemini/config/` to git repositories.
- All secrets referenced in test files and recipes are mapped to internal isolated dev instances.
