FROM python:3.11-slim-bookworm AS builder

# Copy uv from external repository
COPY --from=ghcr.io/astral-sh/uv:0.5.13 /uv /uvx /bin/

# Set the working directory for the build stage
WORKDIR /app

# Copy only necessary files to run the projects
COPY ./bases ./bases
COPY ./components ./components
COPY ./projects/hiscore_scraper .

RUN uv sync --frozen --no-editable
RUN uv build --out-dir ./dist
RUN uv pip install dist/hiscore_scraper-0.1.0-py3-none-any.whl
RUN uv sync --frozen --no-editable

# Production stage: Prepare the final production environment
FROM python:3.11-slim-bookworm AS production
# Copy uv from external repository
COPY --from=ghcr.io/astral-sh/uv:0.5.13 /uv /uvx /bin/
COPY --from=builder --chown=app:app /app/.venv /app/.venv

WORKDIR /app

CMD ["uv","run","hiscore_scraper"]
