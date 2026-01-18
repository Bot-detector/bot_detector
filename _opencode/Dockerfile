# Base image
FROM python:3.12-alpine

# 1. Copy binaries
COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /uvx /bin/
COPY --from=ghcr.io/anomalyco/opencode:1.1.25 /usr/local/bin/opencode /usr/bin/

# 2. Install essential packages for opencode
RUN apk add --no-cache \
    libgcc libstdc++ ripgrep

# 3. Create opencode user and group (UID/GID 1000)
RUN addgroup -g 1000 opencode \
    && adduser -u 1000 -G opencode -D opencode

# 4. Create working directory and fix permissions
RUN mkdir -p /opencode \
    && chown -R opencode:opencode /opencode \
    && chmod 755 /opencode

WORKDIR /opencode

COPY pyproject.toml /opencode/pyproject.toml
COPY uv.lock /opencode/uv.lock

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-install-project

USER opencode

# 7. Default command (optional, can override with ENTRYPOINT)
CMD ["sleep", "infinity"]
# ENTRYPOINT ["opencode"]
