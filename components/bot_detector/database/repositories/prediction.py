import logging
from dataclasses import asdict

import sqlalchemy as sqla
from bot_detector.database.interfaces import (
    PredictionInterface,
    PredictionLatestInterface,
)
from bot_detector.database.structs import (
    PlayersTableStruct,
    PredictionLatestStruct,
    PredictionStruct,
)
from bot_detector.structs import (
    PredictionCreate,
    PredictionLatestRead,
    PredictionRead,
)
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class PredictionLatestRepo(PredictionLatestInterface):
    async def select(
        self,
        async_session: AsyncSession,
        player_name: str | None = None,
        limit: int = 100,
    ) -> list[PredictionLatestRead]:
        logger.info("Selecting all prediction_latest entries")
        limit = max(1, min(limit, 1000))
        sql = sqla.select(PredictionLatestStruct).limit(limit)

        if player_name:
            sql = sql.join(
                PlayersTableStruct,
                PlayersTableStruct.id == PredictionLatestStruct.player_id,
            )
            sql = sql.where(PlayersTableStruct.name == player_name)

        result = await async_session.scalars(sql)
        records = result.all()

        # Convert to Pydantic structs
        predictions = [asdict(record) for record in records]
        predictions = [PredictionLatestRead(**p) for p in predictions]
        return predictions

    async def insert(
        self,
        async_session: AsyncSession,
        predictions: list[PredictionCreate],
    ) -> None:
        logger.info(f"Inserting {len(predictions)} rows into prediction_latest")

        values = [p.model_dump() for p in predictions]
        sql_insert = insert(PredictionLatestStruct).values(values)
        sql_insert = sql_insert.on_duplicate_key_update(
            [
                (key, sql_insert.inserted[key])
                for key in PredictionCreate.model_fields.keys()
            ]
        )
        await async_session.execute(sql_insert)
        await async_session.commit()


class PredictionRepo(PredictionInterface):
    async def select(
        self,
        async_session: AsyncSession,
        player_name: str | None = None,
        limit: int = 100,
    ) -> list[PredictionRead]:
        logger.info("Selecting all prediction entries")

        sql = sqla.select(PredictionStruct).limit(limit)

        if player_name:
            sql = sql.join(
                PlayersTableStruct,
                PlayersTableStruct.id == PredictionStruct.player_id,
            )
            sql = sql.where(PlayersTableStruct.name == player_name)

        result = await async_session.scalars(sql)
        records = result.all()

        # Convert to Pydantic structs
        return [
            PredictionRead.model_validate(record, from_attributes=True)
            for record in records
        ]

    async def insert(
        self,
        async_session: AsyncSession,
        predictions: list[PredictionCreate],
    ) -> None:
        logger.info(f"Inserting {len(predictions)} rows into prediction")

        values = [p.model_dump() for p in predictions]
        sql_insert = insert(PredictionStruct).values(values)
        sql_insert = sql_insert.on_duplicate_key_update(
            [
                (key, sql_insert.inserted[key])
                for key in PredictionCreate.model_fields.keys()
            ]
        )
        await async_session.execute(sql_insert)
        await async_session.commit()
