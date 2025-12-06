FROM python:3.12-slim-bookworm AS base

# Python optimizations
ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1

WORKDIR /app

FROM base AS builder
COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /bin/

COPY ./bases ./bases
COPY ./components ./components
COPY ./projects ./projects

# Install without dev dependencies
RUN --mount=type=cache,id=uv_cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --directory ./projects/api_public

FROM base AS dev
COPY --from=builder /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"

# required for dev dependencies & hot reloading
COPY ./bases ./bases
COPY ./components ./components
COPY ./projects ./projects

# Install with dev dependencies
RUN --mount=type=cache,id=uv_cache,target=/root/.cache/uv \
    uv sync --frozen --directory ./projects/api_public

CMD ["uvicorn", "bot_detector.api_public.src.core.server:app", "--host", "0.0.0.0", "--port", "5000", "--reload"]

FROM base AS prod

# Create a secure user
RUN addgroup --system appuser && \
    adduser --system --ingroup appuser --home /app --no-create-home --disabled-password --uid 5678 appuser

COPY --from=builder --chown=appuser /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"

USER appuser

CMD ["uvicorn", "bot_detector.api_public.src.core.server:app", "--host", "0.0.0.0", "--port", "5000", "--log-level", "warning"]