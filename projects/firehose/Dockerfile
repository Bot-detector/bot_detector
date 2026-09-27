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
COPY ./projects/firehose/Dockerfile ./projects/firehose/Dockerfile
COPY ./projects/firehose/pyproject.toml ./projects/firehose/pyproject.toml
COPY ./projects/firehose/uv.lock ./projects/firehose/uv.lock
COPY workspace.toml workspace.toml

# IMPORTANT: venv path is fixed here
WORKDIR /project/projects/firehose

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
COPY ./projects/firehose/Dockerfile ./projects/firehose/Dockerfile
COPY ./projects/firehose/pyproject.toml ./projects/firehose/pyproject.toml
COPY ./projects/firehose/uv.lock ./projects/firehose/uv.lock
COPY workspace.toml workspace.toml

WORKDIR /project/projects/firehose

RUN --mount=type=cache,id=uv_cache,target=/root/.cache/uv \
    uv sync --dev

# dev-only: import bricks from the bind-mounted sources so hot reload works
RUN rm -rf /project/projects/firehose/.venv/lib/python3.12/site-packages/bot_detector
ENV PYTHONPATH="/project/bases:/project/components"

ENV PATH="/project/projects/firehose/.venv/bin:$PATH"

CMD ["uvicorn", "bot_detector.firehose.core.server:app", "--host", "0.0.0.0", "--port", "5000", "--reload", "--reload-dir", "/project/bases", "--reload-dir", "/project/components", "--timeout-graceful-shutdown", "10"]


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
WORKDIR /project/projects/firehose

# Copy sealed venv (no relocation!)
COPY --from=builder \
    --chown=appuser:appuser \
    /project/projects/firehose/.venv \
    /project/projects/firehose/.venv

ENV PATH="/project/projects/firehose/.venv/bin:$PATH"

USER appuser

CMD ["uvicorn", "bot_detector.firehose.core.server:app", "--host", "0.0.0.0", "--port", "5000", "--log-level", "warning"]
