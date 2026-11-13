from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, model_validator

# Discord embed limits (hard API limits, oversized payloads get 400s)
MAX_EMBEDS_PER_MESSAGE = 10
MAX_FIELDS_PER_EMBED = 25
MAX_TITLE_CHARS = 256
MAX_DESCRIPTION_CHARS = 4096
MAX_FIELD_NAME_CHARS = 256
MAX_FIELD_VALUE_CHARS = 1024
MAX_TOTAL_CHARS = 6000


class EmbedField(BaseModel):
    """A field in a Discord embed. value is rendered as markdown."""

    name: str = Field(max_length=MAX_FIELD_NAME_CHARS)
    value: str = Field(max_length=MAX_FIELD_VALUE_CHARS)
    inline: bool = False


class Embed(BaseModel):
    """A Discord embed message.

    Discord rejects oversized embeds with a 400, which would silently drop
    a broadcast chunk - so the documented limits are enforced here, failing
    fast at construction with a clear message.
    """

    title: str = Field(max_length=MAX_TITLE_CHARS)
    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION_CHARS)
    color: int = 0x000000
    fields: list[EmbedField] = Field(default_factory=list)
    thumbnail_url: str | None = None
    timestamp: datetime | None = None

    @model_validator(mode="after")
    def _check_timestamp_tz(self) -> "Embed":
        # astimezone() treats naive datetimes as system-local time; embeds
        # are UTC, so a naive value would silently shift on the wire
        if self.timestamp is not None and self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        return self

    @model_validator(mode="after")
    def _check_total_size(self) -> "Embed":
        total = len(self.title) + len(self.description or "")
        total += sum(len(f.name) + len(f.value) for f in self.fields)
        if total > MAX_TOTAL_CHARS:
            raise ValueError(
                f"embed total size {total} exceeds Discord limit {MAX_TOTAL_CHARS}"
            )
        if len(self.fields) > MAX_FIELDS_PER_EMBED:
            raise ValueError(
                f"embed has {len(self.fields)} fields, "
                f"Discord allows {MAX_FIELDS_PER_EMBED}"
            )
        return self

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "title": self.title,
            "color": self.color,
            "fields": [field.model_dump() for field in self.fields],
        }
        if self.description is not None:
            payload["description"] = self.description
        if self.thumbnail_url is not None:
            payload["thumbnail"] = {"url": self.thumbnail_url}
        if self.timestamp is not None:
            payload["timestamp"] = self.timestamp.astimezone(timezone.utc).isoformat()
        return payload
