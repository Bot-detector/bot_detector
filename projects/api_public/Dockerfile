FROM python:3.12-slim-bookworm AS builder

# Copy uv from external repository
COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /uvx /bin/

# set the working directory
WORKDIR /app

# Copy only necessary files to run the projects
COPY ./bases ./bases
COPY ./components ./components
COPY ./projects ./projects

WORKDIR /app/projects/api_public

# install dependencies via RUN uv build
RUN uv sync --frozen --no-editable

# Production stage: Prepare the final production environment
FROM python:3.12-slim-bookworm AS production

# Creates a non-root user with an explicit UID and adds permission to access the /project folder
RUN adduser -u 5678 --disabled-password --gecos "" appuser

WORKDIR /app/projects/api_public
COPY --from=base --chown=appuser /app/projects/api_public/.venv /app/projects/api_public/.venv

USER appuser

CMD [".venv/bin/uvicorn", "bot_detector.api_public.src.core.server:app", "--proxy-headers", "--host", "0.0.0.0", "--port", "5000", "--log-level", "warning"]