# syntax=docker/dockerfile:1.7

FROM mcr.microsoft.com/devcontainers/python:3.13@sha256:9b0762901a555c31c2c63824cb5b1ade77da939500e034317b8d09578b94ba0e

ARG NODE_VERSION=20

# Install system dependencies for building Python packages (e.g. psycopg)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# The base image provides the non-root vscode user used by devcontainer.json.
USER vscode
