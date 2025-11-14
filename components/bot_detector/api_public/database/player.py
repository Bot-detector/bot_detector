"""Re-export the shared Players table for API Public consumers."""

from bot_detector.database.player.structs import PlayersTableStruct as Player

__all__ = ["Player"]
