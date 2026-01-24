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
COPY ./projects/worker_hiscore/Dockerfile ./projects/worker_hiscore/Dockerfile
COPY ./projects/worker_hiscore/pyproject.toml ./projects/worker_hiscore/pyproject.toml
COPY ./projects/worker_hiscore/uv.lock ./projects/worker_hiscore/uv.lock
COPY workspace.toml workspace.toml

# IMPORTANT: venv path is fixed here
WORKDIR /project/projects/worker_hiscore

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
COPY ./projects/worker_hiscore/Dockerfile ./projects/worker_hiscore/Dockerfile
COPY ./projects/worker_hiscore/pyproject.toml ./projects/worker_hiscore/pyproject.toml
COPY ./projects/worker_hiscore/uv.lock ./projects/worker_hiscore/uv.lock
COPY workspace.toml workspace.toml

WORKDIR /project/projects/worker_hiscore

RUN --mount=type=cache,id=uv_cache,target=/root/.cache/uv \
    uv sync --dev

ENV PATH="/project/projects/worker_hiscore/.venv/bin:$PATH"

CMD ["worker_hiscore"]


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
WORKDIR /project/projects/worker_hiscore

# Copy sealed venv (no relocation!)
COPY --from=builder \
    --chown=appuser:appuser \
    /project/projects/worker_hiscore/.venv \
    /project/projects/worker_hiscore/.venv

ENV PATH="/project/projects/worker_hiscore/.venv/bin:$PATH"

USER appuser

CMD ["worker_hiscore"]
