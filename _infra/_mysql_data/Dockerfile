FROM python:3.11-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.5.13 /uv /uvx /bin/

WORKDIR /app

COPY _mysql_data/pyproject.toml /app
COPY _mysql_data/uv.lock /app
RUN uv sync

COPY _mysql_data/src /app/src
COPY _shared /app/_shared

CMD ["uv", "run", "src/core.py"]