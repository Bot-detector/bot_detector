import logging
from dataclasses import asdict

import sqlalchemy as sqla
from bot_detector.database.interfaces import playerInterface
from bot_detector.database.structs import PlayerStruct
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# create player
# update player
# get player by id
# get players based on, days since updated, confirmed_Ban, greater than player id with a limit
class PlayerRepo(playerInterface):
    def insert_player(self, player_data: PlayerStruct):
        """Insert a new player into the database."""
        raise NotImplementedError("insert_player method not implemented")

    async def select_player(
        self,
        async_session: AsyncSession,
        days: int = 7,
        confirmed_ban: bool | None = None,
        player_id: int | None = None,
        limit: int = 10_000,
    ) -> list[PlayerStruct]:
        logger.info(f"{player_id=}, {confirmed_ban=}, {days=}, {limit=}")

        sql = sqla.select(PlayerStruct)

        if days:
            sql = sql.where(
                sqla.or_(
                    PlayerStruct.updated_at is None,
                    PlayerStruct.updated_at
                    < sqla.func.now() - sqla.text("interval :days day"),
                )
            )

        if player_id:
            sql = sql.where(PlayerStruct.id > player_id)

        if confirmed_ban is not None:
            sql = sql.where(PlayerStruct.confirmed_ban == confirmed_ban)

        if limit:
            sql = sql.limit(limit)
        sql = sql.order_by(sqla.asc(PlayerStruct.id))

        result = await async_session.scalars(sql, params={"days": days})
        players = result.all()
        return players

    async def update_player(
        self,
        async_session: AsyncSession,
        player_data: PlayerStruct,
    ) -> None:
        """Update an existing player in the database."""
        sql = sqla.update(PlayerStruct)
        sql = sql.where(PlayerStruct.id == player_data.id)
        sql = sql.where(PlayerStruct.updated_at < player_data.updated_at)
        sql = sql.values(asdict(player_data))

        await async_session.execute(sql)

    def delete_player(self, player_id: int):
        """Delete a player from the database by player_id."""
        raise NotImplementedError("delete_player method not implemented")


if __name__ == "__main__":
    import asyncio
    from dataclasses import asdict
    from datetime import datetime

    from bot_detector.database import Settings as DBSettings
    from bot_detector.database import get_session_factory

    player_repo = PlayerRepo()
    async_session, async_engine = get_session_factory(SETTINGS=DBSettings())

    async def main():
        async with async_session() as session:
            async with session.begin():
                players = await player_repo.select_player(
                    async_session=session,
                    confirmed_ban=0,
                    player_id=1,
                    limit=5,
                )
                for player in players:
                    print(asdict(player))
                    print("=" * 50)
                    player.updated_at = datetime.now()
                    await player_repo.update_player(
                        async_session=session, player_data=player
                    )
                await session.commit()

    asyncio.run(main())
