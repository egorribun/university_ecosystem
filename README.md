# University Ecosystem Platform

Unified platform for university life that delivers schedules, news, stories, events, campus map links, user profiles, push notifications, and Spotify integration. The platform has evolved into a microservices architecture to ensure scalability and high performance.

## Prerequisites

- **Python 3.11+** (3.13 recommended) with `pip` and `uv` (optional but recommended)
- **Node.js 20.19+** with `npm`
- **Go 1.24+** (for gateway and WebSocket services)
- **Rust** (for optimization service)
- **Docker & Docker Compose** (required for the full stack)
- **PostgreSQL 17** (with `pgvector` extension)
- **Redis 7** (for caching, rate limiting, and task queues)

## Microservices Architecture

The platform consists of several specialized services:

- **Core API (app/)**: FastAPI-based backend handling business logic, users, and events.
- **Frontend (frontend/)**: Vite + React single-page app with Framer Motion animations.
- **Gateway (services/gateway)**: Go-based entry point for the ecosystem.
- **WS Hub (services/ws-hub)**: High-performance WebSocket server for real-time chat and updates (Go).
- **File Processor (services/file-processor)**: Dedicated service for handling file uploads and metadata (Go).
- **Rust Optimizer (services/rust-optimizer)**: Computational intensive tasks and optimizations (Rust).

### Infrastructure Components
- **Temporal**: Workflow orchestration for reliable background tasks.
- **SpiceDB**: Fine-grained relationship-based access control (ReBAC).
- **MinIO**: High-performance S3-compatible object storage.
- **imgproxy**: On-the-fly image resizing and optimization.
- **NATS**: Lightweight and high-performance messaging system.

## Repository Layout

```
.
├── app/                  # FastAPI application, services, and workers
├── frontend/             # Vite + React single-page app
├── services/             # Microservices (Go, Rust)
│   ├── gateway/          # Go API Gateway
│   ├── file-processor/   # Go service for file handling
│   ├── ws-hub/           # Go WebSocket hub
│   └── rust-optimizer/   # Rust optimization service
├── alembic/              # Database migrations
├── charts/               # Helm charts for Kubernetes deployment
├── docs/                 # Detailed documentation and guides
├── infrastructure/       # Global infrastructure config (Caddyfile, etc.)
├── k8s/                  # Kubernetes manifests
├── scripts/              # Maintenance and automation scripts
├── tests/                # Global and integration test suites
├── docker-compose.yml    # Standard development stack
├── Makefile / justfile   # Unified task management
└── pyproject.toml        # Python project configuration
```

## Getting Started

### 1. Configure Environment

Copy the template and replace placeholder secrets:

```bash
cp .env.example .env
```

Ensure critical values like `DATABASE_URL`, `SECRET_KEY`, and `SPICEDB_PRESHARED_KEY` are correctly set.

### 2. Run the Full Stack (Docker)

The recommended way to start the ecosystem is using Docker Compose:

```bash
docker compose up --build
```

This starts the entire suite, including core services, infrastructure (PostgreSQL, Redis, MinIO, Temporal, SpiceDB), and the frontend.

- **Frontend**: http://localhost:8081
- **Backend API**: http://localhost:8000
- **Gateway**: http://localhost:8080 (optional mapping)
- **WebSocket Hub**: http://localhost:8082
- **Metrics**: http://localhost:8000/metrics

### 3. Database Migrations

Migrations are automatically handled by the `migrations` service in Docker Compose. To run them manually:

```bash
docker compose run --rm backend alembic upgrade head
```

## Platform Capabilities

- **Real-time Communication**: WebSocket-based chat powered by Go `ws-hub` and NATS.
- **Advanced AuthZ**: Relationship-based access control via SpiceDB integration.
- **Reliable Workflows**: Complex background processes orchestrated by Temporal.
- **Media Optimization**: Automatic WebP conversion and resizing via `imgproxy`.
- **Telemetry**: Full-stack observability with OpenTelemetry and Sentry integration.
- **AI-Ready**: Vector search capabilities supported by `pgvector`.

## Development and Testing

### Backend & Python
```bash
# Install dependencies using uv (fast)
uv sync

# Run tests
uv run pytest

# Linting
make lint
```

### Go Services
```bash
cd services/ws-hub
go test ./...
go build -o main .
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

## Documentation

- [Deployment Guide](docs/DEPLOY.md)
- [Localization Guidelines](docs/LOCALIZATION.md)
- [Observability Setup](docs/observability/)
- [Contributing](docs/CONTRIBUTING.md)

---
© 2026 University Ecosystem Team. Happy hacking!
