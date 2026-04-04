FROM python:3.11-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.5.13 /uv /uvx /bin/

WORKDIR /app

COPY _kafka/pyproject.toml /app
COPY _kafka/uv.lock /app
RUN uv sync --frozen

COPY _kafka/src /app/src
COPY _shared /app/_shared

CMD ["uv", "run", "src/core.py"]