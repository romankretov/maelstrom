# syntax=docker/dockerfile:1.7

ARG PYTHON_VERSION=3.12-slim-bookworm

FROM python:${PYTHON_VERSION} AS builder
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /usr/local/bin/

WORKDIR /app
ENV VIRTUAL_ENV=/opt/venv
RUN uv venv "$VIRTUAL_ENV"

COPY apps/worker/pyproject.toml ./pyproject.toml
RUN uv pip compile pyproject.toml -o /tmp/requirements.txt && \
    uv pip install --no-cache -r /tmp/requirements.txt

COPY apps/worker/src ./src
RUN uv pip install --no-cache --no-deps .

# ----------------------------------------------------------------------------
FROM python:${PYTHON_VERSION} AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r app && useradd -r -g app -d /app -s /usr/sbin/nologin app
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app /app
USER app
CMD ["arq", "maelstrom_worker.main.WorkerSettings"]
