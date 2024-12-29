# Build stage: Use uv to build the wheel
FROM python:3.11-slim-bookworm AS builder

# Copy uv from external repository
COPY --from=ghcr.io/astral-sh/uv:0.5.13 /uv /uvx /bin/

# Set the working directory for the build stage
WORKDIR /app

# Copy only necessary files for building the wheel
COPY ./projects/hiscore_scraper/pyproject.toml .
COPY ./projects/hiscore_scraper/uv.lock .
COPY ./projects/hiscore_scraper/ .

# Build the wheel using uv
RUN uv build --out-dir ./dist

# Production stage: Prepare the final production environment
FROM python:3.11-slim-bookworm AS production

# Copy uv from the builder stage
COPY --from=ghcr.io/astral-sh/uv:0.5.13 /uv /uvx /bin/

# Copy the built wheel from the build stage
WORKDIR /app
COPY --from=builder /app/dist/ .
COPY --from=builder /app/pyproject.toml .
COPY --from=builder /app/uv.lock .
# Install the wheel using uv
# RUN uv install --wheel ./dist/*.whl

# Run the package using uv
CMD ["uv", "run", "hiscore_scraper"]
