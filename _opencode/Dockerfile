FROM python:3.12-slim-bookworm AS base

# Create dedicated user with home directory
RUN addgroup --gid 1000 opencode \
    && adduser --uid 1000 --gid 1000 --disabled-password --gecos "" --home /home/opencode opencode \
    && mkdir -p /home/opencode \
    && chown -R opencode:opencode /home/opencode

ENV HOME=/home/opencode
WORKDIR /home/opencode

FROM base AS final

USER opencode

# Ensure necessary directories exist
RUN mkdir -p $HOME/.local/bin $HOME/.bun/bin $HOME/.local/state

# Ensure full XDG directory structure for uv / uvx
RUN mkdir -p \
    $HOME/.local/bin \
    $HOME/.local/share/uv \
    $HOME/.local/state \
    $HOME/.cache \
    && chown -R opencode:opencode $HOME/.local $HOME/.cache

# Copy prebuilt binaries
COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /uvx $HOME/.local/bin/
COPY --from=oven/bun:debian /usr/local/bin/bun $HOME/.local/bin/

# Set PATH
ENV PATH=$HOME/.local/bin:$HOME/.bun/bin:$PATH
ENV OPENCODE_DISABLE_AUTOUPDATE=1

# Install global Bun packages (no cache, binaries persist)
RUN bun add -g opencode-ai@1.1.9 @ast-grep/cli

WORKDIR /home/opencode/project

# Copy project dependency files
COPY pyproject.toml pyproject.toml
COPY uv.lock uv.lock

# Sync Python project dependencies with cache
RUN --mount=type=cache,target=$HOME/.cache/uv,uid=1000,gid=1000 \
    uv sync --no-install-project

# CMD ["sleep", "infinity"]
ENTRYPOINT ["opencode"]
