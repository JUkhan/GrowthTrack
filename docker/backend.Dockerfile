# Shared image for the api and scheduler containers (AD-5: separate containers,
# same codebase — only the compose `command:` differs between them).
FROM python:3.13-slim AS base

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

RUN groupadd --system app \
    && useradd --system --gid app --home-dir /app --shell /usr/sbin/nologin app

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY api/ api/
COPY domain/ domain/
COPY ports/ ports/
COPY adapters/ adapters/
COPY scheduler/ scheduler/
COPY scripts/ scripts/
COPY alembic/ alembic/
COPY alembic.ini config.py ./

RUN uv sync --frozen --no-dev \
    && chown -R app:app /app

USER app

ENV PATH="/app/.venv/bin:$PATH"
