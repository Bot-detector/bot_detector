FROM python:3.12-slim-bookworm AS base

# Python optimizations
ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1

WORKDIR /app

FROM base AS builder
COPY --from=ghcr.io/astral-sh/uv:0.5.13 /uv /bin/

WORKDIR /app

COPY ./projects/job_prune_hs_data ./projects/job_prune_hs_data
COPY ./bases ./bases
COPY ./components ./components

RUN --mount=type=cache,id=uv_cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --project ./projects/job_prune_hs_data

FROM base AS dev
COPY --from=ghcr.io/astral-sh/uv:0.5.13 /uv uvx/ /bin/
COPY --from=builder /app/projects/job_prune_hs_data/.venv /app/.venv

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"

COPY ./projects/job_prune_hs_data ./projects/job_prune_hs_data
COPY ./bases ./bases
COPY ./components ./components

RUN --mount=type=cache,id=uv_cache,target=/root/.cache/uv \
    uv sync --dev --project ./projects/job_prune_hs_data \
    && cp -r projects/job_prune_hs_data/.venv/ .venv/

CMD [".venv/bin/job_prune_hs_data"]

FROM base AS prod

WORKDIR /app

# Create a secure user
RUN addgroup --system appuser && \
    adduser --system --ingroup appuser --home /app --no-create-home --disabled-password --uid 5678 appuser

COPY --from=builder --chown=appuser /app/projects/job_prune_hs_data/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"

USER appuser

CMD [".venv/bin/job_prune_hs_data"]
