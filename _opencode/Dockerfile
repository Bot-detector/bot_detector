FROM python:3.12-slim-bookworm AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    libatomic1 \
    && rm -rf /var/lib/apt/lists/*

FROM base AS base_installer

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl unzip \
    && rm -rf /var/lib/apt/lists/*

# install opencode
FROM base_installer AS opencode_installer
RUN curl -fsSL https://opencode.ai/install | bash

FROM base AS final

# Copy all binaries
COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /uvx /bin/
COPY --from=oven/bun:debian /usr/local/bin/bun /usr/local/bin/
COPY --from=opencode_installer /root/.opencode/bin/opencode /usr/local/bin/

# Set up PATH
ENV PATH=/usr/local/bin:/home/opencode/.local/bin:$PATH

WORKDIR /project

# Create dedicated user
RUN addgroup --gid 1000 opencode \
    && adduser --uid 1000 --gid 1000 --disabled-password --gecos "" opencode \
    && chown -R opencode:opencode /project /home/opencode/

USER opencode

RUN --mount=type=cache,target=/home/opencode/.bun/,uid=1000,gid=1000 \
    bun x oh-my-opencode install --no-tui --claude=no --openai=no --gemini=no --copilot=no --opencode-zen=no --zai-coding-plan=no

RUN --mount=type=cache,target=/home/opencode/.bun/,uid=1000,gid=1000 \
    bun install @ast-grep/cli

COPY pyproject.toml pyproject.toml
COPY uv.lock uv.lock

RUN --mount=type=cache,target=/home/opencode/.cache/uv,uid=1000,gid=1000 \
    uv sync --no-install-project

# CMD ["sleep", "infinity"] 
ENTRYPOINT ["opencode"]
