FROM python:3.11-slim-bookworm AS builder

# Copy uv from external repository
COPY --from=ghcr.io/astral-sh/uv:0.5.13 /uv /uvx /bin/

# Set the working directory for the build stage
WORKDIR /app

# Copy only necessary files to run the projects
COPY ./bases ./bases
COPY ./components ./components
COPY ./projects ./projects

WORKDIR /app/projects/job_hs_migration_v3

# RUN uv build
RUN uv sync --frozen --no-editable

# Production stage: Prepare the final production environment
FROM python:3.11-slim-bookworm AS production

RUN adduser -u 5678 --disabled-password --gecos "" appuser

WORKDIR /app/projects/job_hs_migration_v3

COPY --from=builder --chown=appuser /app/projects/job_hs_migration_v3/.venv /app/projects/job_hs_migration_v3/.venv

USER appuser

CMD [".venv/bin/job_hs_migration_v3"]
