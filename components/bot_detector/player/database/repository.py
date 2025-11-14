import logging
from dataclasses import asdict
from datetime import date

import sqlalchemy as sqla
from .interface import playerInterface
from .structs import PlayersTableStruct
from bot_detector.player.structs import PlayerStruct
from sqlalchemy import TextClause
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# create player
# update player
# get player by id
# get players based on, days since updated, confirmed_Ban, greater than player id with a limit
class PlayerRepo(playerInterface):
    def insert_player(self, player_data: PlayerStruct) -> None:
        """Insert a new player into the database."""
        raise NotImplementedError("insert_player method not implemented")

    async def select_player(
        self,
        async_session: AsyncSession,
        or_none: bool = False,
        first_date: date | None = None,
        last_date: date | None = None,
        confirmed_ban: bool | None = None,
        possible_ban: bool | None = None,
        player_id: int | None = None,
        limit: int = 10_000,
    ) -> list[PlayerStruct]:
        logger.info(
            f"{player_id=}, {confirmed_ban=}, {possible_ban=}, {first_date=}, {last_date=}, {limit=}"
        )

        sql = sqla.select(PlayersTableStruct)

        # length of the name should be <= 13
        sql = sql.where(sqla.func.length(PlayersTableStruct.name) <= 13)

        if first_date and last_date:
            _stmt = PlayersTableStruct.updated_at.between(first_date, last_date)
            if or_none:
                _stmt = sqla.or_(_stmt, PlayersTableStruct.updated_at.is_(None))

            sql = sql.where(_stmt)

        if player_id:
            sql = sql.where(PlayersTableStruct.id > player_id)

        if confirmed_ban is not None:
            sql = sql.where(PlayersTableStruct.confirmed_ban == confirmed_ban)

        if possible_ban is not None:
            sql = sql.where(PlayersTableStruct.possible_ban == possible_ban)

        if limit:
            sql = sql.limit(limit)

        sql = sql.order_by(sqla.asc(PlayersTableStruct.id))

        result = await async_session.scalars(sql)
        players = result.all()
        players_dict = [asdict(player) for player in players]
        players_struct = [PlayerStruct(**player_dict) for player_dict in players_dict]
        return players_struct

    def _create_temp_player(self) -> TextClause:
        """Create a temporary player table for the latest data."""
        return sqla.text(
            """
            CREATE TEMPORARY TABLE temp_player_data (
                id BIGINT NOT NULL,
                name VARCHAR(255) NOT NULL,
                updated_at TIMESTAMP DEFAULT NULL,
                possible_ban BOOLEAN NOT NULL DEFAULT '0',
                confirmed_ban BOOLEAN NOT NULL DEFAULT '0',
                confirmed_player BOOLEAN NOT NULL DEFAULT '0',
                label_id INTEGER NOT NULL DEFAULT '0',
                label_jagex INTEGER NOT NULL DEFAULT '0'
            ) ENGINE=MEMORY;
            """
        )

    def _insert_temp_player(self) -> TextClause:
        """Insert data into the temporary player table."""
        return sqla.text(
            """
            INSERT INTO temp_player_data (id, name, updated_at, possible_ban, confirmed_ban, confirmed_player, label_id, label_jagex) 
            VALUES (:id, :name, :updated_at, :possible_ban, :confirmed_ban, :confirmed_player, :label_id, :label_jagex);
            """
        )

    def _update_player(self) -> TextClause:
        """Update the player data in the main table from the temporary table."""

        return sqla.text(
            """
            UPDATE Players AS p
            JOIN temp_player_data AS t ON p.id = t.id
            SET 
                p.updated_at = t.updated_at,
                p.possible_ban = t.possible_ban,
                p.confirmed_ban = t.confirmed_ban,
                p.confirmed_player = t.confirmed_player,
                p.label_id = t.label_id,
                p.label_jagex = t.label_jagex
            WHERE 1=1
                AND (p.updated_at < t.updated_at OR p.updated_at IS NULL);
            """
        )

    async def update_many_players(
        self,
        async_session: AsyncSession,
        players_data: list[PlayerStruct],
    ) -> None:
        """Update multiple players in the database."""
        if not players_data:
            return

        _data = [p.model_dump() for p in players_data]

        drop_temp_table = sqla.text("DROP TEMPORARY TABLE IF EXISTS temp_player_data;")
        # Drop temporary table if it exists
        await async_session.execute(drop_temp_table)

        # Create temporary table
        await async_session.execute(self._create_temp_player())

        # Insert data into temporary table
        await async_session.execute(self._insert_temp_player(), _data)

        # Update main table from temporary table
        await async_session.execute(self._update_player())

        # Drop temporary table if it exists
        await async_session.execute(drop_temp_table)
        return

    async def update_player(
        self,
        async_session: AsyncSession,
        player_data: PlayerStruct,
    ) -> None:
        """Update an existing player in the database."""
        sql = sqla.update(PlayersTableStruct)
        sql = sql.where(PlayersTableStruct.id == player_data.id)
        sql = sql.where(
            sqla.or_(
                PlayersTableStruct.updated_at < player_data.updated_at,
                PlayersTableStruct.updated_at.is_(None),
            )
        )
        sql = sql.values(player_data.model_dump())

        await async_session.execute(sql)

    def delete_player(self, player_id: int):
        """Delete a player from the database by player_id."""
        raise NotImplementedError("delete_player method not implemented")
