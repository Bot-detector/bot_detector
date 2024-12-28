# Base stage
FROM python:3.11-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.5.13 /uv /uvx /bin/

# Set the working directory
WORKDIR /app

# Copy the project configuration files
COPY ./pyproject.toml /app
COPY ./workspace.toml /app
COPY ./uv.lock /app
COPY ./README.md /app

# Sync dependencies with uv
RUN uv sync --frozen

# Copy all components, bases, and projects
COPY ./bases /app/bases
COPY ./components /app/components
COPY ./bases /app/development
COPY ./bases /app/projects

# Set the entry point for the application
CMD ["uv", "run", "bases/bot_detector/hiscore_scraper/core.py"]
 