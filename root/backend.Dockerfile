# syntax=docker/dockerfile:1.6

FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

FROM base AS builder
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*
COPY root/requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip \
    && pip install --prefix=/install -r requirements.txt

FROM base AS runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
RUN groupadd --system app \
    && useradd --system --gid app --create-home app
COPY --from=builder --chown=app:app /install /usr/local
COPY --chown=app:app root/app ./app
COPY --chown=app:app root/alembic ./alembic
COPY --chown=app:app root/alembic.ini ./alembic.ini
COPY --chown=app:app root/create_invite_code.py ./create_invite_code.py
ENV PYTHONPATH="/app"
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 CMD curl -f http://localhost:8000/healthz || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
