FROM ghcr.io/astral-sh/uv:python3.12-trixie-slim@sha256:d4a752dd52f42e0c508bb0b6a912f15922bb32e42f66af30671c3fdc0d759f21

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
