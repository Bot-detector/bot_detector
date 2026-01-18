FROM python:3.12-slim-bookworm AS base

FROM base AS base_installer

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl unzip \
    && rm -rf /var/lib/apt/lists/*

# install bun
FROM base_installer AS bun_installer
RUN curl -fsSL https://bun.sh/install | bash

# install opencode
FROM base_installer AS opencode_installer
RUN curl -fsSL https://opencode.ai/install | bash


FROM base AS final

# Copy all binaries
COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /uvx /bin/
COPY --from=opencode_installer /root/.opencode/bin/opencode /usr/local/bin/
COPY --from=bun_installer /root/.bun/bin/bun /usr/local/bin/
# Set up PATH
ENV PATH=/usr/local/bin:$PATH

# install oh-my-opencode
RUN bun install -g oh-my-opencode

WORKDIR /project

# Create dedicated user
RUN addgroup --gid 1000 opencode \
    && adduser --uid 1000 --gid 1000 --disabled-password --gecos "" opencode \
    && chown -R opencode:opencode /project

# Set up user directories
RUN mkdir -p /home/opencode/.local/share/opencode \
    && chown -R opencode:opencode /home/opencode/.local

USER opencode

COPY pyproject.toml pyproject.toml
COPY uv.lock uv.lock

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-install-project

# CMD ["sleep", "infinity"] 
ENTRYPOINT ["opencode"]
