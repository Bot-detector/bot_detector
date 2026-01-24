FROM python:3.12-slim-bookworm AS base

# Python optimizations
ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1

WORKDIR /app

FROM base AS builder
COPY --from=ghcr.io/astral-sh/uv:0.5.13 /uv /bin/

WORKDIR /app

COPY ./projects/website ./projects/website
COPY ./bases ./bases
COPY ./components ./components

RUN --mount=type=cache,id=uv_cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --project ./projects/website

FROM base AS dev
COPY --from=ghcr.io/astral-sh/uv:0.5.13 /uv uvx/ /bin/
COPY --from=builder /app/projects/website/.venv /app/.venv

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"

COPY ./projects/website ./projects/website
COPY ./bases ./bases
COPY ./components ./components

RUN --mount=type=cache,id=uv_cache,target=/root/.cache/uv \
    uv sync --dev --project ./projects/website \
    && cp -r projects/website/.venv/ .venv/

CMD ["uvicorn", "bot_detector.website.core.server:app", "--host", "0.0.0.0", "--port", "5000", "--reload"]

FROM base AS prod

WORKDIR /app

# Create a secure user
RUN addgroup --system appuser && \
    adduser --system --ingroup appuser --home /app --no-create-home --disabled-password --uid 5678 appuser

COPY --from=builder --chown=appuser /app/projects/website/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"

USER appuser

CMD [".venv/bin/uvicorn", "bot_detector.website.core.server:app", "--proxy-headers", "--host", "0.0.0.0", "--port", "5000", "--log-level", "warning"]
