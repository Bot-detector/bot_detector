FROM python:3.12-slim-bookworm AS base

# Copy binaries
COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /uvx /bin/

FROM base AS opencode_base

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl 

# install to /root/.opencode/bin/opencode
RUN curl -fsSL https://opencode.ai/install | bash

FROM opencode_base AS build

COPY --from=opencode_base /root/.opencode/bin/opencode /usr/local/bin/

WORKDIR /project

RUN addgroup --gid 1000 opencode \
    && adduser --uid 1000 --gid 1000 --disabled-password --gecos "" opencode \
    && chown -R opencode:opencode /project

# fix permissions
RUN mkdir -p /home/opencode/.local/share/opencode \
    && chown -R opencode:opencode /home/opencode/.local

USER opencode

COPY pyproject.toml pyproject.toml
COPY uv.lock uv.lock

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-install-project

# CMD ["sleep", "infinity"] 
ENTRYPOINT ["opencode"]
