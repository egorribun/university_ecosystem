# syntax=docker/dockerfile:1.7

# Stage 1: Builder
FROM python:3.13.1-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_COLOR=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

RUN --mount=type=cache,id=apt-lists-builder,target=/var/lib/apt/lists \
    --mount=type=cache,id=apt-cache-builder,target=/var/cache/apt \
    apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv accurately
COPY --from=ghcr.io/astral-sh/uv:0.5.21 /uv /uv/bin/uv
ENV PATH="/uv/bin:$PATH" \
    UV_PROJECT_ENVIRONMENT="/opt/venv"

# Create virtual environment and install dependencies
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Stage 2: Runtime
FROM python:3.13.1-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Install tini for better signal handling and curl for healthchecks
RUN --mount=type=cache,id=apt-lists-runtime,target=/var/lib/apt/lists \
    --mount=type=cache,id=apt-cache-runtime,target=/var/cache/apt \
    apt-get update \
    && apt-get install -y --no-install-recommends tini curl \
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

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/healthz || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
