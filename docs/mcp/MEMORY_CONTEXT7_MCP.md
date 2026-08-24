# Persistent Memory & Live Documentation Guide (Memory & Context7 MCP)

## 1. Overview & Cognitive Architecture

Autonomous multi-agent workflows require both persistent cross-session state (what the team has decided, built, and verified) and real-time, authoritative documentation (current library APIs, type signatures, and best practices):

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 Autonomous Subagent Suite                                   │
│                       (Lead Architect, TDD Dev, Security Auditor)                           │
└──────────────────────────────┬───────────────────────────────┬──────────────────────────────┘
                               │                               │
                               ▼                               ▼
               ┌───────────────────────────────┐ ┌───────────────────────────────┐
               │           Memory MCP          │ │          Context7 MCP         │
               │   (@modelcontextprotocol)     │ │     (mcp.context7.com)        │
               ├───────────────────────────────┤ ├───────────────────────────────┤
               │ • Entity-Relation Graph       │ │ • Live API Documentation      │
               │ • Cross-Turn Architectural ADR│ │ • FastAPI / SQLAlchemy 2.0    │
               │ • Invariant Persistence       │ │ • Dishka DI / Valibot         │
               │ • Service Boundary Mapping    │ │ • TanStack Router / React 19  │
               └───────────────────────────────┘ └───────────────────────────────┘
```

- **Memory MCP (`memory`)**: Provides an entity-relation knowledge graph stored locally on disk. Enables agents to persist architectural decisions, ADR citations, discovered gotchas, and multi-step investigation findings across turns.
- **Context7 MCP (`context7`)**: Provides up-to-date, version-accurate documentation directly from official library sources, preventing hallucinations of deprecated APIs or syntax patterns.

---

## 2. Persistent Memory MCP (`memory`)

### 2.1 Knowledge Graph Data Model

The Memory MCP server organizes knowledge into two primary structures:
1. **Entities**:
   - `name: string` (Unique identifier / title)
   - `entityType: string` (e.g. `ArchitectureDecision`, `ServiceBoundary`, `SecurityPolicy`, `InvariantGotcha`, `PerformanceTarget`)
   - `observations: string[]` (List of factual statements or rules)
2. **Relations**:
   - `from: string` (Source entity name)
   - `to: string` (Target entity name)
   - `relationType: string` (e.g. `DEPENDS_ON`, `ENFORCES`, `MIGRATED_FROM`, `CACHES_TO`, `COMMUNICATES_VIA`)

### 2.2 Tool Reference Matrix

| Tool Name | Parameters | Description |
|---|---|---|
| `create_entities` | `entities: Array<{name: string, entityType: string, observations: string[]}>` | Inserts new knowledge entities into the persistent graph. |
| `create_relations` | `relations: Array<{from: string, to: string, relationType: string}>` | Creates directed relationship edges between entities. |
| `add_observations` | `observations: Array<{entityName: string, contents: string[]}>` | Appends new observations to existing entities. |
| `read_graph` | *(none)* | Dumps the entire entity-relation graph. |
| `search_nodes` | `query: string` | Performs semantic / text search across entity names, types, and observations. |
| `open_nodes` | `names: string[]` | Retrieves specific entities and their incoming/outgoing relations by name. |
| `delete_entities` | `entityNames: string[]` | Removes entities and their associated relations from the graph. |
| `delete_relations` | `relations: Array<{from: string, to: string, relationType: string}>` | Removes specific relationship edges. |

---

### 2.3 Practical Memory Recipes

#### Recipe 1: Initializing Architectural Decisions & Invariants

```json
// Step 1: Create core architectural entities
{
  "ServerName": "memory",
  "ToolName": "create_entities",
  "Arguments": {
    "entities": [
      {
        "name": "ADR-012: Centralized Logging",
        "entityType": "ArchitectureDecision",
        "observations": [
          "Adopted Grafana Loki and Fluent Bit for centralized log aggregation.",
          "All microservices stream structured JSON logs."
        ]
      },
      {
        "name": "ADR-013: Secret Rotation Strategy",
        "entityType": "ArchitectureDecision",
        "observations": [
          "Three-tier secret rotation policy.",
          "Dual-key RS256 JWT window allowing rolling key rotation without downtime."
        ]
      },
      {
        "name": "Backend Data Access Rule",
        "entityType": "InvariantGotcha",
        "observations": [
          "All SQLAlchemy relationships must declare explicit lazy='noload'.",
          "All exception blocks must use tuple syntax except (A, B): narrowed to specific types."
        ]
      }
    ]
  }
}

// Step 2: Create relation edges
{
  "ServerName": "memory",
  "ToolName": "create_relations",
  "Arguments": {
    "relations": [
      {
        "from": "Backend Data Access Rule",
        "to": "ADR-013: Secret Rotation Strategy",
        "relationType": "ENFORCES"
      }
    ]
  }
}
```

#### Recipe 2: Querying Context Prior to Execution

```json
{
  "ServerName": "memory",
  "ToolName": "search_nodes",
  "Arguments": {
    "query": "lazy=noload"
  },
  "toolAction": "Search knowledge graph",
  "toolSummary": "Search architectural rules on relationships"
}
```

---

## 3. Real-Time Documentation MCP (`context7`)

### 3.1 Two-Stage Documentation Lookup Workflow

Context7 provides a reliable two-step protocol for extracting live documentation:

```
    ┌──────────────────────────┐           ┌──────────────────────────┐
    │ 1. resolve-library-id    │           │ 2. query-docs            │
    │    (Query: "fastapi")    │ ────────► │    (libraryId: "/fastapi"│
    │    Returns: "/fastapi"   │           │     topic: "lifespan")   │
    └──────────────────────────┘           └──────────────────────────┘
```

1. **`resolve-library-id`**:
   - `query: string` (e.g. `"fastapi"`, `"sqlalchemy"`, `"dishka"`, `"valibot"`, `"tanstack-router"`)
   - Resolves human-readable search string to the exact Context7 library ID.
2. **`query-docs`**:
   - `libraryId: string` (The resolved library ID, e.g. `"/fastapi"`)
   - `query: string` (Specific API, class, method, or pattern needed)
   - Returns focused markdown documentation chunks.

---

### 3.2 Live Documentation Recipes for Repository Stack

#### Recipe 1: FastAPI 0.115+ & Pydantic V2 Lifespan Handlers

```json
// Step 1: Resolve FastAPI library identifier
{
  "ServerName": "context7",
  "ToolName": "resolve-library-id",
  "Arguments": {
    "query": "fastapi"
  }
}

// Step 2: Query lifespan and dependency injection documentation
{
  "ServerName": "context7",
  "ToolName": "query-docs",
  "Arguments": {
    "libraryId": "/fastapi",
    "query": "async lifespan contextmanager app setup and shutdown"
  }
}
```

---

#### Recipe 2: SQLAlchemy 2.0 Async Session & CTE Invariants

```json
// Step 1: Resolve SQLAlchemy library identifier
{
  "ServerName": "context7",
  "ToolName": "resolve-library-id",
  "Arguments": {
    "query": "sqlalchemy"
  }
}

// Step 2: Query CTE and selectinload async querying
{
  "ServerName": "context7",
  "ToolName": "query-docs",
  "Arguments": {
    "libraryId": "/sqlalchemy",
    "query": "async session selectinload relationship and recursive cte queries"
  }
}
```

---

#### Recipe 3: Dishka Dependency Injection Container & Scopes

```json
// Step 1: Resolve Dishka library identifier
{
  "ServerName": "context7",
  "ToolName": "resolve-library-id",
  "Arguments": {
    "query": "dishka"
  }
}

// Step 2: Query Provider and Scope configuration
{
  "ServerName": "context7",
  "ToolName": "query-docs",
  "Arguments": {
    "libraryId": "/dishka",
    "query": "Provider Scope.REQUEST provide async generator dependency injection with FastAPI"
  }
}
```

---

#### Recipe 4: Valibot Schema Validation (v0.30+ / v1.0)

```json
// Step 1: Resolve Valibot library identifier
{
  "ServerName": "context7",
  "ToolName": "resolve-library-id",
  "Arguments": {
    "query": "valibot"
  }
}

// Step 2: Query schema composition and pipe validation
{
  "ServerName": "context7",
  "ToolName": "query-docs",
  "Arguments": {
    "libraryId": "/valibot",
    "query": "pipe string email minLength safeParse schema definition"
  }
}
```

---

#### Recipe 5: TanStack Router & Query File-Based Route Invariants

```json
// Step 1: Resolve TanStack Router identifier
{
  "ServerName": "context7",
  "ToolName": "resolve-library-id",
  "Arguments": {
    "query": "tanstack-router"
  }
}

// Step 2: Query loader and search param schema validation
{
  "ServerName": "context7",
  "ToolName": "query-docs",
  "Arguments": {
    "libraryId": "/tanstack-router",
    "query": "createFileRoute loader validateSearch with valibot beforeLoad redirect"
  }
}
```

---

## 4. Operational Best Practices

1. **Always Resolve Before Querying**: Never guess the `libraryId` for Context7. Always execute `resolve-library-id` first.
2. **Keep Entity Observations Atomic**: In Memory MCP, split complex decisions into individual, concise statements within `observations` to maximize vector and text search recall.
3. **Link Entities with Expressive Relations**: Use specific relation verbs (`ENFORCES`, `DEPENDS_ON`, `SUPERSEDES`, `CACHES_TO`) to construct meaningful subgraphs.
