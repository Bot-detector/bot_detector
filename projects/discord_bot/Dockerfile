# === Base stage ===
FROM python:3.12-slim AS base

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astralys/uv:latest /usr/local/bin/uv

# Copy dependency files
COPY pyproject.toml /app/
COPY uv.lock /app/

# Copy bricks
COPY components/bot_detector/database /app/bot_detector/database
COPY components/bot_detector/public_api /app/bot_detector/public_api
COPY components/bot_detector/osrs_items /app/bot_detector/osrs_items
COPY components/bot_detector/logfmt /app/bot_detector/logfmt
COPY bases/bot_detector/discord_bot /app/bot_detector/discord_bot

# Sync dependencies
RUN uv sync --frozen

# === Prod stage ===
FROM python:3.12-slim AS prod

WORKDIR /app

COPY --from=base /app/.venv /app/.venv
COPY --from=base /app/bot_detector /app/bot_detector
COPY --from=base /app/uv.lock /app/

# Create non-root user
RUN useradd --create-home --shell /bin/sh appuser && \
    chown -R appuser:appuser /app

USER appuser

# Run the bot
CMD ["python", "-m", "bot_detector.discord_bot.core"]
