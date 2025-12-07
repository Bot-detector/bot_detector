FROM python:3.12-slim-bookworm AS base

# Python optimizations
ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1

WORKDIR /app

FROM base AS builder
COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /bin/

COPY ./pyproject.toml ./uv.lock ./
COPY ./bases ./bases
COPY ./components ./components

RUN --mount=type=cache,id=uv_cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

FROM base AS dev
COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv uvx/ /bin/

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"

COPY ./projects/api_public/pyproject.toml ./projects/api_public/uv.lock ./
COPY ./bases ./bases
COPY ./components ./components

# this isntalls dev dependencies
RUN --mount=type=cache,id=uv_cache,target=/root/.cache/uv \
    uv sync --frozen

CMD [ "sleep", "infinity" ]