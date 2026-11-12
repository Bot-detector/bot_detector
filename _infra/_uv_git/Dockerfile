# CI base image: uv + git on Debian bookworm-slim.
# Used by .github/workflows/_common.yml where job steps need both
# uv (pytest, poly diff) and git (actions/checkout, git merge-base).
# ghcr.io/astral-sh/uv:bookworm-slim has no git, so it is added here.
# Base image is pinned by digest for reproducible CI runs; bump it
# deliberately when upgrading uv.
FROM ghcr.io/astral-sh/uv:bookworm-slim@sha256:22334efe746f1b69217d455049b484d7b8cacfb2d5f42555580b62415a98e0a3

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
