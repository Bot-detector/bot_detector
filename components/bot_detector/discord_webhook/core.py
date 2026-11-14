import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import aiohttp
import orjson

from .interface import WebhookInterface
from .structs import MAX_EMBEDS_PER_MESSAGE, MAX_TOTAL_CHARS, Embed

logger = logging.getLogger(__name__)

RATE_LIMIT_RETRIES = 3
POST_TIMEOUT_SECONDS = 30
DEFAULT_RETRY_AFTER_SECONDS = 1.0
# Cron-window bound: a hostile or honest huge retry_after (Discord global
# limits, misconfigured proxies) must cost cap * attempts, not park the
# whole broadcast run past its window.
MAX_RETRY_AFTER_SECONDS = 60.0


class DiscordWebhookRepo(WebhookInterface):
    """Posts embed messages to Discord webhook URLs over aiohttp.

    Honors 429 rate-limit responses by sleeping retry_after and retrying,
    replacing the blocking discord_webhook library's rate_limit_retry. Every
    post is retried uniformly - the legacy job skipped rate-limit retries on
    its names-chunk posts and silently lost those embeds on 429s.

    Errors are returned as values (never raised) so a single failed post can
    be logged without aborting a broadcast loop. CancelledError still
    propagates.
    """

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self.session = session

    async def post(
        self,
        url: str,
        embeds: list[Embed] | None = None,
        content: str | None = None,
    ) -> Exception | None:
        if embeds and len(embeds) > MAX_EMBEDS_PER_MESSAGE:
            return Exception(
                f"webhook post refused: {len(embeds)} embeds exceeds "
                f"Discord limit {MAX_EMBEDS_PER_MESSAGE}"
            )
        if embeds:
            # the 6000-char limit binds per message across all embeds,
            # not per embed (docs: "across all embeds attached to a message")
            total = sum(embed.char_count() for embed in embeds)
            if total > MAX_TOTAL_CHARS:
                return Exception(
                    f"webhook post refused: embed total {total} chars exceeds "
                    f"Discord limit {MAX_TOTAL_CHARS} for one message"
                )
        if not embeds and not content:
            return Exception(
                "webhook post refused: empty payload (no embeds, no content)"
            )
        payload: dict[str, Any] = {}
        if embeds:
            payload["embeds"] = [embed.to_payload() for embed in embeds]
        if content:
            payload["content"] = content

        for attempt in range(1, RATE_LIMIT_RETRIES + 1):
            try:
                async with self.session.post(
                    url,
                    data=orjson.dumps(payload),
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=POST_TIMEOUT_SECONDS),
                    # never replay the payload to a redirect target
                    allow_redirects=False,
                ) as resp:
                    if resp.status in (200, 204):
                        return None
                    if resp.status == 429:
                        if attempt == RATE_LIMIT_RETRIES:
                            break
                        retry_after = min(
                            max(await self._rate_limit_seconds(resp), 0.0),
                            MAX_RETRY_AFTER_SECONDS,
                        )
                        logger.warning(
                            f"webhook post rate limited, retry {attempt}/"
                            f"{RATE_LIMIT_RETRIES} in {retry_after}s"
                        )
                        await asyncio.sleep(retry_after)
                        continue
                    body = await resp.text()
                    return Exception(
                        f"webhook post failed status={resp.status} body={body}"
                    )
            except (aiohttp.ClientError, TimeoutError) as exc:
                return Exception(f"webhook post failed: {exc}")

        return Exception(
            f"webhook post still rate limited after {RATE_LIMIT_RETRIES} attempts"
        )

    async def _rate_limit_seconds(self, resp: aiohttp.ClientResponse) -> float:
        """Discord's 429 body carries retry_after in fractional seconds
        (64.57-style) and is authoritative; the Retry-After header is its
        integer ceiling (65) and only fills in when the body omits or
        garbles the value. Anything unreadable falls back to a sane default.
        """
        try:
            data = await resp.json()
            retry_after = float(data["retry_after"]) if isinstance(data, dict) else None
        except (
            aiohttp.ContentTypeError,
            ValueError,
            TypeError,  # retry_after: null or a non-numeric JSON value
            AttributeError,  # non-object JSON body (list, string, null)
            KeyError,  # object body without retry_after: header decides next
        ):
            retry_after = None
        if retry_after is not None:
            return retry_after
        header_value = resp.headers.get("Retry-After")
        if header_value:
            try:
                return float(header_value)
            except ValueError:
                pass
        return DEFAULT_RETRY_AFTER_SECONDS


def utcnow() -> datetime:
    """Discord expects UTC timestamps for embeds."""
    return datetime.now(tz=timezone.utc)
