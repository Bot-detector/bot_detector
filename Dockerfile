FROM python:3.12-slim-bookworm AS builder

# Copy uv from external repository
COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /uvx /bin/

# Set the working directory for the build stage
WORKDIR /app

# Copy only necessary files for installing dependencies
COPY ./pyproject.toml .
COPY ./uv.lock .
COPY ./README.md .

# RUN uv cache dir
# RUN uv sync


CMD [ "sleep", "infinity" ]