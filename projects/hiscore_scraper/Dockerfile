# Base stage
FROM python:3.11-slim-bookworm AS base
COPY --from=ghcr.io/astral-sh/uv:0.5.13 /uv /uvx /bin/

# Set the working directory
WORKDIR /app

# Copy the project configuration files
COPY ./projects/hiscore_scraper/pyproject.toml /app
COPY ./projects/hiscore_scraper/uv.lock /app

# Sync dependencies with uv
RUN uv sync --frozen

# Copy all components, bases, and projects
COPY ./components ./app/components
COPY ./bases ./app/bases
COPY ./projects ./app/projects

# Set the entry point for the application
CMD ["uv", "run", "hiscore_scraper"]
