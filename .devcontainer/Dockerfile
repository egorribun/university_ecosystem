# syntax=docker/dockerfile:1.7

FROM mcr.microsoft.com/devcontainers/python:3.13

ARG NODE_VERSION=20

# Install system dependencies for building Python packages (e.g. psycopg)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Pre-install backend dependencies to speed up container start
COPY root/requirements.txt /tmp/pip-tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/pip-tmp/requirements.txt \
    && rm -rf /tmp/pip-tmp

WORKDIR /workspace
