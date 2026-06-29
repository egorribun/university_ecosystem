# syntax=docker/dockerfile:1.12

# Rust toolchain stage — provides a known-good Cargo/rustc for maturin builds.
# Rust 1.85 is the first stable release supporting edition 2024 and Cargo.lock v4.
FROM rust:1.94.1-slim-bookworm@sha256:5ae2d2ef9875c9c2407bf9b5678e6375304f7ecf8ea46b23e403a5690ec357ec AS rust-toolchain

# Stage 1: Builder
# MOD-21-08 (Wave 21): Updated to Python 3.14 for free-threading support,
# deferred annotation evaluation (PEP 649), and improved error messages.
FROM python:3.14-slim-bookworm@sha256:4ff4b92a68355dbdb52584ab3391dff8d371a61d4e063468bfd0130e3189c6d9 AS builder

# Pin uv to an exact version for reproducible builds.
# Use 0.10.8 for proven stability in current scan environments.
COPY --from=ghcr.io/astral-sh/uv:0.11.2 /uv /uv/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /build

# Update OS packages and install build dependencies.
# Rust toolchain is copied from the rust-toolchain stage instead of using
# the stale apt package (Debian bookworm ships Cargo 1.63 which does not
# support edition 2024 or Cargo.lock format v4).
RUN --mount=type=cache,id=apt-lists-builder,target=/var/lib/apt/lists \
    --mount=type=cache,id=apt-cache-builder,target=/var/cache/apt \
    apt-get update \
    && apt-get dist-upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*
RUN python -m pip install --no-cache-dir --upgrade pip==26.0

# Copy Rust toolchain from the dedicated stage.
COPY --from=rust-toolchain /usr/local/cargo /usr/local/cargo
COPY --from=rust-toolchain /usr/local/rustup /usr/local/rustup

ENV RUSTUP_HOME=/usr/local/rustup \
    CARGO_HOME=/usr/local/cargo \
    PATH="/uv/bin:/usr/local/cargo/bin:$PATH" \
    UV_PROJECT_ENVIRONMENT="/opt/venv"

# Copy workspace member sources so uv can resolve the lockfile.
# pyo3-sanitizer and rust_ext are local Rust/PyO3 extensions declared as
# workspace members in pyproject.toml — uv requires them at sync time.
COPY crates ./crates
COPY native ./native

# Create virtual environment and install dependencies
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=cache,target=/root/.cargo/registry \
    uv sync --frozen --no-dev --no-install-project

# Stage 2: Runtime
FROM python:3.14-slim-bookworm@sha256:4ff4b92a68355dbdb52584ab3391dff8d371a61d4e063468bfd0130e3189c6d9 AS runtime

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
    && useradd --system --uid 10001 --gid app --home-dir /home/app --shell /usr/sbin/nologin --no-create-home app
RUN python -m pip install --no-cache-dir --upgrade pip==26.0

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

# TD-007 (audit 2026-03-19): Use gunicorn as process manager with uvicorn workers
# Workers = 2 × CPU + 1 (using 2 workers for baseline memory limits).
# --graceful-timeout 30: matches terminationGracePeriodSeconds in K8s
CMD ["gunicorn", "app.main:app", \
    "--worker-class", "uvicorn.workers.UvicornWorker", \
    "--workers", "2", \
    "--bind", "0.0.0.0:8000", \
    "--graceful-timeout", "30", \
    "--timeout", "60", \
    "--keep-alive", "5", \
    "--access-logfile", "-", \
    "--error-logfile", "-"]
