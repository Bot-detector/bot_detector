FROM python:3.11-slim-bookworm AS builder

# Copy uv from external repository
COPY --from=ghcr.io/astral-sh/uv:0.5.13 /uv /uvx /bin/

# Set the working directory for the build stage
WORKDIR /app

# Copy only necessary files for installing dependencies
COPY ./pyproject.toml .
COPY ./uv.lock .
COPY ./README.md .

RUN uv sync

# Copy only necessary files to run the projects
COPY ./bases ./bases
COPY ./components ./components
COPY ./projects ./projects

CMD [ "sleep", "infinity" ]