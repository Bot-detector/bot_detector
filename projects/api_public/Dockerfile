FROM python:3.11-slim AS base

# Copy uv from external repository
COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /uvx /bin/

# set environment variables
ARG api_port
ENV UVICORN_PORT=${api_port}

ARG root_path
ENV UVICORN_ROOT_PATH=${root_path}

# set the working directory
WORKDIR /app

# Copy only necessary files to run the projects
COPY ./bases ./bases
COPY ./components ./components
COPY ./projects ./projects

WORKDIR /app/projects/api_public

# install dependencies via RUN uv build
RUN uv sync --frozen --no-editable

# copy the scripts to the folder
# COPY ./src /project/src

# Production stage: Prepare the final production environment
FROM python:3.11-slim AS production

# Creates a non-root user with an explicit UID and adds permission to access the /project folder
RUN adduser -u 5678 --disabled-password --gecos "" appuser

WORKDIR /app/projects/api_public
COPY --from=base --chown=appuser /app/projects/api_public/.venv /app/projects/api_public/.venv

USER appuser

CMD ["uvicorn", "src.core.server:app", "--proxy-headers", "--host", "0.0.0.0", "--log-level", "warning"]