# Base stage
FROM python:3.11-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.5.13 /uv /uvx /bin/

ARG wheel=hiscore_scraper-0.1.0-py3-none-any.whl

# This is when using workspaces, and when exported the requirements
ARG deps=requirements.txt

RUN python -m pip install --upgrade pip

WORKDIR /code

COPY ./dist/$wheel /code/$wheel
COPY ./$deps /code/$deps

# This is adjusted to install third-party dependencies separately (the --no-deps) and install from requirements
RUN pip install --no-cache-dir --upgrade --no-deps /code/$wheel
RUN pip install -r /code/$deps

# Set the entry point for the application
CMD ["uv", "run", "bases/bot_detector/hiscore_scraper/core.py"]
 