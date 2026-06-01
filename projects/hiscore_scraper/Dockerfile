# ------------------------------------------------------------
# Base (shared env only, no filesystem assumptions)
# ------------------------------------------------------------
FROM python:3.12-slim-bookworm AS base

ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1

WORKDIR /project


# ------------------------------------------------------------
# Builder: runtime-only venv (path is FINAL)
# ------------------------------------------------------------
FROM base AS builder

COPY --from=ghcr.io/astral-sh/uv:0.5.13 /uv /bin/uv
COPY ./bases ./bases
COPY ./components ./components
COPY ./projects/hiscore_scraper/Dockerfile ./projects/hiscore_scraper/Dockerfile
COPY ./projects/hiscore_scraper/pyproject.toml ./projects/hiscore_scraper/pyproject.toml
COPY ./projects/hiscore_scraper/uv.lock ./projects/hiscore_scraper/uv.lock
COPY workspace.toml workspace.toml

# IMPORTANT: venv path is fixed here
WORKDIR /project/projects/hiscore_scraper

RUN --mount=type=cache,id=uv_cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ------------------------------------------------------------
# Dev: full workspace + dev deps (own venv)
# ------------------------------------------------------------
FROM base AS dev

COPY --from=ghcr.io/astral-sh/uv:0.5.13 /uv /uvx /bin/

ENV PYTHONPATH="/project"

COPY ./bases ./bases
COPY ./components ./components
COPY ./projects/hiscore_scraper/Dockerfile ./projects/hiscore_scraper/Dockerfile
COPY ./projects/hiscore_scraper/pyproject.toml ./projects/hiscore_scraper/pyproject.toml
COPY ./projects/hiscore_scraper/uv.lock ./projects/hiscore_scraper/uv.lock
COPY workspace.toml workspace.toml

WORKDIR /project/projects/hiscore_scraper

RUN --mount=type=cache,id=uv_cache,target=/root/.cache/uv \
    uv sync --dev

ENV PATH="/project/projects/hiscore_scraper/.venv/bin:$PATH"

CMD ["hiscore_scraper"]


# ------------------------------------------------------------
# Prod: minimal, secure, venv-only runtime
# ------------------------------------------------------------
FROM base AS prod

# Non-root user
RUN addgroup --system appuser && \
    adduser --system --ingroup appuser \
            --uid 1000 --disabled-password \
            --no-create-home appuser

# SAME PATH as builder
WORKDIR /project/projects/hiscore_scraper

# Copy sealed venv (no relocation!)
COPY --from=builder \
    --chown=appuser:appuser \
    /project/projects/hiscore_scraper/.venv \
    /project/projects/hiscore_scraper/.venv

ENV PATH="/project/projects/hiscore_scraper/.venv/bin:$PATH"

EXPOSE 8000

USER appuser

CMD ["hiscore_scraper"]
