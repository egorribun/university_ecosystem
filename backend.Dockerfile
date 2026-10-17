# syntax=docker/dockerfile:1.27.1@sha256:4edf897a3ffa55b89f906fc8cc78afdb3f1834cc9c7083565e611a8a7d5fe99e

# Rust toolchain stage — provides a known-good Cargo/rustc for maturin builds.
# Rust 1.85 is the first stable release supporting edition 2024 and Cargo.lock v4.
FROM rust:1.99.0-slim-bookworm@sha256:2c3a22f0a5533ea2dd5a16627bc841228151faa2d4de2644ac9987e4a2f1f2fa AS rust-toolchain

# Stage 1: Builder
# MOD-21-08 (Wave 21): Updated to Python 3.14 for free-threading support,
# deferred annotation evaluation (PEP 649), and improved error messages.
FROM python:3.14.8-slim-bookworm@sha256:48b13b003dda20b16f9442b8475aa05fe21bf6579a8c881db92ffb4d8fd20f83 AS builder

# Pin uv to the same exact version enforced by pyproject.toml. The digest is
# the linux/amd64 manifest for uv 0.12.23, the platform used by CI and release
# image builds.
COPY --from=ghcr.io/astral-sh/uv:0.12.23@sha256:61d393e44e249f2e4b526b6c7ddcecce245946826e608e11c93ad4f5bba55b21 /uv /uv/bin/uv

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
    && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Rust toolchain from the dedicated stage.
COPY --from=rust-toolchain /usr/local/cargo /usr/local/cargo
COPY --from=rust-toolchain /usr/local/rustup /usr/local/rustup

ENV RUSTUP_HOME=/usr/local/rustup \
    CARGO_HOME=/usr/local/cargo \
    PATH="/uv/bin:/usr/local/cargo/bin:$PATH" \
    UV_PROJECT_ENVIRONMENT="/opt/venv"

# Copy workspace member sources so uv can resolve the lockfile.
# rust_ext is a local Rust/PyO3 extension declared as a workspace member in
# pyproject.toml — uv requires it at sync time.
COPY native ./native

# Create virtual environment and install dependencies
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=cache,target=/root/.cargo/registry \
    n=0; until uv sync --frozen --no-dev --no-install-project; do \
        n=$((n + 1)); \
        if [ "$n" -ge 5 ]; then \
            echo "uv sync failed after $n attempts" >&2; \
            exit 1; \
        fi; \
        echo "uv sync failed (network), retry $n/5 in 5s..." >&2; \
        sleep 5; \
    done

# Stage 2: Runtime
FROM python:3.14.8-slim-bookworm@sha256:48b13b003dda20b16f9442b8475aa05fe21bf6579a8c881db92ffb4d8fd20f83 AS runtime

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
    && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends tini \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /home/app --shell /usr/sbin/nologin --create-home app

# Runtime keeps the locked application venv; remove the base image's global pip
# and the bundled ensurepip wheel that contains the same vulnerable vendored code.
RUN python -c "import pathlib, sys; p=pathlib.Path(sys.prefix)/'lib'/f'python{sys.version_info.major}.{sys.version_info.minor}'/'ensurepip'; assert sys.version_info[:2] == (3, 14); assert sys.prefix == '/usr/local'; assert p == pathlib.Path('/usr/local/lib/python3.14/ensurepip'); assert p.is_dir() and not p.is_symlink()" \
    && python -m pip uninstall --yes pip \
    && rm -rf /usr/local/lib/python3.14/ensurepip \
    && python -c "import importlib.util, pathlib, sys; p=pathlib.Path(sys.prefix)/'lib'/f'python{sys.version_info.major}.{sys.version_info.minor}'/'ensurepip'; assert sys.version_info[:2] == (3, 14); assert sys.prefix == '/usr/local'; assert not p.exists(); assert importlib.util.find_spec('pip') is None; assert importlib.util.find_spec('ensurepip') is None"
# Copy virtual environment from builder
COPY --from=builder --chown=app:app /opt/venv /opt/venv
RUN /opt/venv/bin/python -c "import fastapi, sqlalchemy, urllib3; assert urllib3.__version__ == '2.8.0'"

# Copy application source
COPY --chown=app:app app ./app
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app alembic.ini ./alembic.ini

# Ensure cache directory exists with correct permissions
RUN mkdir -p /app/cache && chown -R app:app /app/cache

USER 10001:10001

EXPOSE 8000

# Use Python stdlib urllib — no external binaries required.
# Keep the image-level probe aligned with the Kubernetes readiness contract.
# `/health/ready` checks database connectivity and honors graceful shutdown;
# the more expensive `/healthz` endpoint is reserved for diagnostics.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=4)"]

ENTRYPOINT ["/usr/bin/tini", "--"]

# TD-007 (audit 2026-03-19): Use gunicorn as process manager with uvicorn workers
# Workers = 2 × CPU + 1 (using 2 workers for baseline memory limits).
# --graceful-timeout 30: matches terminationGracePeriodSeconds in K8s
# Access logging is intentionally disabled: UvicornWorker writes the full ASGI
# request target, including its query string, through uvicorn.access.
CMD ["gunicorn", "app.main:app", \
    "--worker-class", "uvicorn.workers.UvicornWorker", \
    "--workers", "2", \
    "--bind", "0.0.0.0:8000", \
    "--graceful-timeout", "30", \
    "--timeout", "60", \
    "--keep-alive", "5", \
    "--error-logfile", "-"]
