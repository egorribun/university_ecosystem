# syntax=docker/dockerfile:1.7

# Stage 1: Builder
FROM python:3.12-slim-bookworm AS builder

# Pin uv to an exact version for reproducible builds.
# Use 0.10.6 for proven stability in current scan environments.
COPY --from=ghcr.io/astral-sh/uv:0.10.6 /uv /uv/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /build

# Update OS packages and install build dependencies.
RUN --mount=type=cache,id=apt-lists-builder,target=/var/lib/apt/lists \
    --mount=type=cache,id=apt-cache-builder,target=/var/cache/apt \
    apt-get update \
    && apt-get dist-upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends \
       build-essential \
       curl \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/uv/bin:$PATH" \
    UV_PROJECT_ENVIRONMENT="/opt/venv"

# Create virtual environment and install dependencies
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Stage 2: Runtime
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Dump a Python traceback on SIGSEGV/SIGFPE/SIGABRT/SIGBUS/SIGILL — aids debugging.
    PYTHONFAULTHANDLER=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Install tini for proper signal handling (PID-1 reaping).
# curl is intentionally omitted — healthcheck uses Python stdlib instead,
# reducing the attack surface by one CVE-prone binary.
# apt-get upgrade ensures Debian security patches released after the base
# image was built on Docker Hub are applied at our build time.
RUN --mount=type=cache,id=apt-lists-runtime,target=/var/lib/apt/lists \
    --mount=type=cache,id=apt-cache-runtime,target=/var/cache/apt \
    apt-get update \
    && apt-get dist-upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends tini \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /home/app --shell /bin/bash app

# Copy virtual environment from builder
COPY --from=builder --chown=app:app /opt/venv /opt/venv

# Copy application source
COPY --chown=app:app app ./app
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app alembic.ini ./alembic.ini

# Ensure cache directory exists with correct permissions
RUN mkdir -p /app/cache && chown -R app:app /app/cache

USER app

EXPOSE 8000

# Use Python stdlib urllib — no external binaries required.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)"

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
