# ------------------------------------------------------------
# Base (shared env only, no filesystem assumptions)
# ------------------------------------------------------------
FROM python:3.12-slim-bookworm AS base

ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1

WORKDIR /project


# ------------------------------------------------------------
# Builder: production dependencies only
# ------------------------------------------------------------
FROM base AS builder

COPY --from=ghcr.io/astral-sh/uv:0.5.13 /uv /bin/uv
COPY ./bases ./bases
COPY ./components ./components
COPY ./projects/scrape_task_producer/Dockerfile ./projects/scrape_task_producer/Dockerfile
COPY ./projects/scrape_task_producer/pyproject.toml ./projects/scrape_task_producer/pyproject.toml
COPY ./projects/scrape_task_producer/uv.lock ./projects/scrape_task_producer/uv.lock
COPY workspace.toml workspace.toml

# IMPORTANT: venv path is fixed here
WORKDIR /project/projects/scrape_task_producer

RUN --mount=type=cache,id=uv_cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


# ------------------------------------------------------------
# Dev: development environment with dev dependencies
# ------------------------------------------------------------
FROM base AS dev

COPY --from=ghcr.io/astral-sh/uv:0.5.13 /uv /uvx /bin/

ENV PYTHONPATH="/project"

COPY ./bases ./bases
COPY ./components ./components
COPY ./projects/scrape_task_producer/Dockerfile ./projects/scrape_task_producer/Dockerfile
COPY ./projects/scrape_task_producer/pyproject.toml ./projects/scrape_task_producer/pyproject.toml
COPY ./projects/scrape_task_producer/uv.lock ./projects/scrape_task_producer/uv.lock
COPY workspace.toml workspace.toml

WORKDIR /project/projects/scrape_task_producer

RUN --mount=type=cache,id=uv_cache,target=/root/.cache/uv \
    uv sync --dev

ENV PATH="/project/projects/scrape_task_producer/.venv/bin:$PATH"

CMD ["scrape_task_producer"]


# ------------------------------------------------------------
# Prod: minimal, secure, venv-only runtime
# ------------------------------------------------------------
FROM python:3.12-slim-bookworm AS prod

# Non-root user
RUN addgroup --system appuser && \
    adduser --system --ingroup appuser \
            --uid 1000 --disabled-password \
            --no-create-home appuser

# SAME PATH as builder
WORKDIR /project/projects/scrape_task_producer

# Copy sealed venv (no relocation!)
COPY --from=builder \
    --chown=appuser:appuser \
    /project/projects/scrape_task_producer/.venv \
    /project/projects/scrape_task_producer/.venv

ENV PATH="/project/projects/scrape_task_producer/.venv/bin:$PATH"

USER appuser

CMD ["scrape_task_producer"]
