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

WORKDIR /opencode

COPY pyproject.toml pyproject.toml
COPY uv.lock uv.lock

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-install-project

# Create opencode user and group (UID/GID 1000)
RUN addgroup --gid 1000 opencode

# create user with UID 1000, primary group opencode, home directory, no password
RUN adduser --uid 1000 --gid 1000 --disabled-password --gecos "" opencode

USER opencode

CMD ["sleep", "infinity"] 

# ENTRYPOINT ["opencode"]
