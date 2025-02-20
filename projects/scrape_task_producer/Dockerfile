FROM python:3.11-slim-bookworm AS builder

# Copy uv from external repository
COPY --from=ghcr.io/astral-sh/uv:0.5.13 /uv /uvx /bin/

# Set the working directory for the build stage
WORKDIR /app

# Copy only necessary files to run the projects
COPY ./bases ./bases
COPY ./components ./components
COPY ./projects ./projects

WORKDIR /app/projects/scrape_task_producer

# RUN uv build
RUN uv sync --frozen --no-editable

# Production stage: Prepare the final production environment
FROM python:3.11-slim-bookworm AS production

WORKDIR /app/projects/scrape_task_producer

COPY --from=builder --chown=app:app /app/projects/scrape_task_producer/.venv /app/projects/scrape_task_producer/.venv

CMD [".venv/bin/scrape_task_producer"]
