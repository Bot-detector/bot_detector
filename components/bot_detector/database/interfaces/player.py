from abc import ABC, abstractmethod

from bot_detector.database.structs.player import PlayerStruct


class playerInterface(ABC):
    @abstractmethod
    def insert_player(self, player_data):
        """Insert a new player into the database."""
        pass

    @abstractmethod
    def select_player(self, player_id: int):
        """Select a player from the database by player_id."""
        pass

    @abstractmethod
    def update_player(self, player_id: int, player_data: PlayerStruct):
        """Update an existing player in the database."""
        pass

    @abstractmethod
    def delete_player(self, player_id: int):
        """Delete a player from the database by player_id."""
        pass
