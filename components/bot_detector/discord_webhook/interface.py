from abc import ABC, abstractmethod

from .structs import Embed


class WebhookInterface(ABC):
    @abstractmethod
    async def post(
        self,
        url: str,
        embeds: list[Embed] | None = None,
        content: str | None = None,
    ) -> Exception | None:
        """Post a message to a Discord webhook.

        Returns None on success, or an Exception if the post failed after
        retries. Errors are returned as values so a single failed post can
        be logged without aborting a broadcast loop.
        """
        raise NotImplementedError()
