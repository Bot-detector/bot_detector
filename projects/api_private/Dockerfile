FROM python:3.12-slim-bookworm AS base

# Copy uv from external repository
COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /uvx /bin/

# set the working directory
WORKDIR /app

# Copy only necessary files to run the projects
COPY ./bases ./bases
COPY ./components ./components
COPY ./projects ./projects

WORKDIR /app/projects/api_private

# install dependencies via RUN uv build
RUN uv sync --frozen --no-editable

# Production stage: Prepare the final production environment
FROM python:3.12-slim-bookworm AS production

# Creates a non-root user with an explicit UID and adds permission to access the /project folder
RUN adduser -u 5678 --disabled-password --gecos "" appuser

WORKDIR /app/projects/api_private
COPY --from=base --chown=appuser /app/projects/api_private/.venv /app/projects/api_private/.venv

USER appuser

CMD [".venv/bin/uvicorn", "bot_detector.api_private.src.core.server:app", "--proxy-headers", "--host", "0.0.0.0", "--port", "6000", "--log-level", "warning"]