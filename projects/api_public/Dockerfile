# ------------------------------------------------------------
# Base (shared env only, no filesystem assumptions)
# ------------------------------------------------------------
FROM python:3.12-slim-bookworm AS base

# Python optimizations
ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1

WORKDIR /project


# ------------------------------------------------------------
# Builder: production dependencies only
# ------------------------------------------------------------
FROM base AS builder

COPY --from=ghcr.io/astral-sh/uv:0.5.13 /uv /bin/

WORKDIR /project

COPY ./projects/api_public ./projects/api_public
COPY ./bases ./bases
COPY ./components ./components

RUN --mount=type=cache,id=uv_cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --project ./projects/api_public


# ------------------------------------------------------------
# Dev: development environment with dev dependencies
# ------------------------------------------------------------
FROM base AS dev

COPY --from=ghcr.io/astral-sh/uv:0.5.13 /uv uvx/ /bin/

WORKDIR /project

ENV PATH="/project/.venv/bin:$PATH"
ENV PYTHONPATH="/project"

COPY ./projects/api_public ./projects/api_public
COPY ./bases ./bases
COPY ./components ./components

RUN --mount=type=cache,id=uv_cache,target=/root/.cache/uv \
    uv sync --dev --project ./projects/api_public \
    && cp -r projects/api_public/.venv/ .venv/

CMD ["uvicorn", "bot_detector.api_public.src.core.server:app", "--host", "0.0.0.0", "--port", "5000", "--reload"]


# ------------------------------------------------------------
# Prod: minimal, secure, venv-only runtime
# ------------------------------------------------------------
FROM base AS prod

WORKDIR /project

# Create a secure user
RUN addgroup --system appuser && \
    adduser --system --ingroup appuser --home /project --no-create-home --disabled-password --uid 1000 appuser

COPY --from=builder --chown=appuser /project/projects/api_public/.venv /project/.venv

ENV PATH="/project/.venv/bin:$PATH"
ENV PYTHONPATH="/project"

USER appuser

CMD ["python3", "-m", "uvicorn", "bot_detector.api_public.src.core.server:app", "--host", "0.0.0.0", "--port", "5000", "--log-level", "warning"]
