# Base stage
FROM python:3.11-slim-bookworm as base
COPY --from=ghcr.io/astral-sh/uv:0.5.13 /uv /uvx /bin/

# set the working directory
WORKDIR /project

COPY ./pyproject.toml /project
COPY ./uv.lock /project
RUN uv sync --frozen

# copy the scripts to the folder
COPY ./src /project/src

# Production stage for highscore
FROM base as production-highscore
# Creates a non-root user with an explicit UID and adds permission to access the /project folder
RUN adduser -u 5678 --disabled-password --gecos "" appuser && chown -R appuser /project
USER appuser

CMD ["python", "src/main_highscore.py"]