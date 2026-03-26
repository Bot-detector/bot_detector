FROM python:3.11-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.5.13 /uv /uvx /bin/

WORKDIR /app

COPY ./pyproject.toml /app
COPY ./uv.lock /app
RUN uv sync --frozen

COPY ./src /app/src

# Set the KAFKA_BROKER environment variable during container runtime
# ENV KAFKA_BROKER=localhost:9094
CMD ["uv", "run", "src/core.py"]