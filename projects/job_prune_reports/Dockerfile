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
COPY ./projects/job_prune_reports/Dockerfile ./projects/job_prune_reports/Dockerfile
COPY ./projects/job_prune_reports/pyproject.toml ./projects/job_prune_reports/pyproject.toml
COPY ./projects/job_prune_reports/uv.lock ./projects/job_prune_reports/uv.lock
COPY workspace.toml workspace.toml

# IMPORTANT: venv path is fixed here
WORKDIR /project/projects/job_prune_reports

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
COPY ./projects/job_prune_reports/Dockerfile ./projects/job_prune_reports/Dockerfile
COPY ./projects/job_prune_reports/pyproject.toml ./projects/job_prune_reports/pyproject.toml
COPY ./projects/job_prune_reports/uv.lock ./projects/job_prune_reports/uv.lock
COPY workspace.toml workspace.toml

WORKDIR /project/projects/job_prune_reports

RUN --mount=type=cache,id=uv_cache,target=/root/.cache/uv \
    uv sync --dev

ENV PATH="/project/projects/job_prune_reports/.venv/bin:$PATH"

CMD ["job_prune_reports"]


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
WORKDIR /project/projects/job_prune_reports

# Copy sealed venv (no relocation!)
COPY --from=builder \
    --chown=appuser:appuser \
    /project/projects/job_prune_reports/.venv \
    /project/projects/job_prune_reports/.venv

ENV PATH="/project/projects/job_prune_reports/.venv/bin:$PATH"

USER appuser

CMD ["job_prune_reports"]
