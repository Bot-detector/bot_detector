from dataclasses import dataclass

from aiohttp import ClientSession
from bot_detector.firehose.app.auth.auth import ApiKeyAuthRepo
from bot_detector.firehose.app.auth.discord import DiscordOAuth
from bot_detector.firehose.app.connection_manager import ConnectionManager
from bot_detector.firehose.app.consumer import QueueRepo
from bot_detector.firehose.app.consumer_manager import ConsumerManager
from bot_detector.firehose.core.config import Settings


@dataclass
class FirehoseState:
    """Typed application state; attached to app.state as `firehose`."""

    settings: Settings
    queue_repo: QueueRepo
    auth_repo: ApiKeyAuthRepo
    consumer_manager: ConsumerManager
    connection_manager: ConnectionManager
    http_session: ClientSession | None = None
    discord_oauth: DiscordOAuth | None = None


def get_state(app) -> FirehoseState:
    """Typed accessor for the application state."""
    state: FirehoseState = app.state.firehose
    return state
