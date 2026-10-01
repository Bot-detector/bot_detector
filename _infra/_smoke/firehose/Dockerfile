FROM python:3.12-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.5.13 /uv /uvx /bin/

WORKDIR /app

COPY _smoke/firehose/pyproject.toml /app
COPY _smoke/firehose/uv.lock /app
RUN --mount=type=cache,id=uv_cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

COPY _smoke/firehose/src /app/src

CMD ["uv", "run", "src/smoke.py"]
