import asyncio
import json
import logging
import time
from datetime import timedelta

import sqlalchemy as sqla
from bot_detector.database import Settings as DBSettings
from bot_detector.database import get_session_factory
from bot_detector.event_queue.adapters.kafka import (
    KafkaConfig,
    KafkaProducerConfig,
    KafkaSettings,
)
from bot_detector.event_queue.core import QueueProducer
from bot_detector.event_queue.factory import QueueFactory
from bot_detector.event_queue.structs import ScrapedStruct
from bot_detector.structs import (
    HighscoreBaseStruct,
    MetaData,
    PlayerStruct,
)
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from sqlalchemy import TextClause
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    LIMIT: int = 10000


async def get_latest_player_id(
    session_factory: async_sessionmaker[AsyncSession],
) -> int:
    async with session_factory() as session:
        async with session.begin():
            result = await session.execute(
                sqla.text("SELECT player_id FROM migration_hs_v3;")
            )
            latest_player_id = result.scalar_one_or_none() or 0
            return latest_player_id


async def update_latest_player_id(
    session_factory: async_sessionmaker[AsyncSession], player_id: int
):
    async with session_factory() as session:
        async with session.begin():
            await session.execute(
                sqla.text("UPDATE migration_hs_v3 SET player_id = :player_id;"),
                params={"player_id": player_id},
            )


def _records_to_migrate() -> TextClause:
    sql = sqla.text("""
        SELECT 
            pl.id as player_id,
            pl.name as player_name,
            pl.created_at,
            pl.updated_at,
            pl.possible_ban,
            pl.confirmed_ban,
            pl.confirmed_player,
            pl.label_id,
            pl.label_jagex,
            sdv.scrape_date,
            (
                SELECT JSON_OBJECTAGG(s.skill_name, ps.skill_value)
                FROM scraper_player_skill sps
                JOIN player_skill ps ON sps.player_skill_id = ps.player_skill_id
                JOIN skill s ON ps.skill_id = s.skill_id
                WHERE sps.scrape_id = sdv.scrape_id
            ) AS skills,
            (
                SELECT JSON_OBJECTAGG(a.activity_name, pa.activity_value)
                FROM scraper_player_activity spa
                JOIN player_activity pa ON spa.player_activity_id = pa.player_activity_id
                JOIN activity a ON pa.activity_id = a.activity_id
                WHERE spa.scrape_id = sdv.scrape_id
            ) AS activities
        FROM scraper_data_v3 sdv
        join Players pl on sdv.player_id = pl.id
        where 1=1
            and pl.id > :player_id 
        ORDER BY pl.id asc
        limit :limit
        ;
    """)
    return sql


async def get_hiscore_data(
    session_factory: async_sessionmaker[AsyncSession],
    params: dict,
) -> list[dict]:
    logger.info(f"Query: {params=}")
    start_time = time.time()

    assert params.keys() == {"player_id", "limit"}

    async with session_factory() as session:
        async with session.begin():
            result = await session.execute(_records_to_migrate(), params)
            data = result.mappings().all()
            # to list of dict
            data = [dict(row) for row in data]

    duration = time.time() - start_time
    logger.info(f"Result: {len(data)}, {params=}, time={duration:.2f}")
    return data


def json_to_struct(data: list[dict]) -> list[ScrapedStruct]:
    _data = []
    for d in data:
        skills = json.loads(d["skills"]) if d["skills"] else {}
        skills = {k.lower(): v for k, v in skills.items()}
        activities = json.loads(d["activities"]) if d["activities"] else {}
        activities = {k.lower(): v for k, v in activities.items()}

        scraped_struct = ScrapedStruct(
            metadata=MetaData(version=1, source="migration_v3"),
            player_data=PlayerStruct(
                id=d["player_id"],
                name=d["player_name"],
                created_at=d["created_at"],
                updated_at=d["updated_at"],
                possible_ban=d["possible_ban"],
                confirmed_ban=d["confirmed_ban"],
                confirmed_player=d["confirmed_player"],
                label_id=d["label_id"],
                label_jagex=d["label_jagex"],
            ),
            highscore_data=HighscoreBaseStruct(
                player_id=d["player_id"],
                scrape_date=d["scrape_date"],
                time_to_live=d["scrape_date"],
                skills=skills,
                activities=activities,
            ),
        )
        if scraped_struct.player_data.updated_at:
            scraped_struct.player_data.updated_at -= timedelta(days=1)
        _data.append(scraped_struct)
    return _data


async def producer_send(
    producer: QueueProducer[ScrapedStruct],
    stop_event: asyncio.Event,
    queue: asyncio.Queue,
):
    try:
        while True:
            task = await queue.get()
            data, params = task["data"], task["params"]
            len_data = len(data)
            logger.info(f"Received: {len_data}, {params}")
            start_time = time.time()

            while data:
                put_results = await asyncio.gather(
                    *[producer.put([d]) for d in data],
                    return_exceptions=True,
                )
                # Filter out failed messages for retry
                data = [
                    d for d, r in zip(data, put_results) if isinstance(r, Exception)
                ]

                if data:
                    logger.warning(f"{len(data)} messages failed, retrying...")
                    await asyncio.sleep(1)
            duration = time.time() - start_time
            logger.info(f"Produced: {len_data}, {params=}, time={duration:.2f}")
            queue.task_done()
    except Exception as e:
        logger.error(f"Fatal error in producer_send: {e}")
        stop_event.set()


async def main():
    async_session, async_engine = get_session_factory(SETTINGS=DBSettings())
    b_server = KafkaSettings().bootstrap_servers

    def partition_key_fn(message: BaseModel) -> str:
        assert isinstance(message, ScrapedStruct)
        return str(message.player_data.id % 10)

    queue = QueueFactory.create_queue(
        model=ScrapedStruct,
        queue_type="producer",
        backend_type="kafka",
        config=KafkaConfig(
            topic="players.scraped",
            bootstrap_servers=b_server,
            producer=True,
            producer_config=KafkaProducerConfig(partition_key_fn=partition_key_fn),
        ),
    )
    if isinstance(queue, Exception):
        raise queue
    assert isinstance(queue, QueueProducer)
    player_sc_producer = queue
    produce_queue = asyncio.Queue(maxsize=1)
    stop_event = asyncio.Event()

    await player_sc_producer.start()
    _ = asyncio.create_task(
        producer_send(
            producer=player_sc_producer,
            queue=produce_queue,
            stop_event=stop_event,
        )
    )
    params = {"player_id": 0, "limit": Settings().LIMIT}

    while not stop_event.is_set():
        player_id = await get_latest_player_id(async_session)
        params["player_id"] = player_id

        try:
            data = await get_hiscore_data(
                session_factory=async_session,
                params=params,
            )
        except OperationalError as e:
            logger.info(f"{params=}, {e=}")
            continue
        except Exception as e:
            logger.error(f"{params=}, {e=}")
            break
        if not data:
            logger.error("no data")
            break

        scraped_structs = json_to_struct(data=data)
        item = {"data": scraped_structs, "params": params.copy()}
        await produce_queue.put(item=item)
        del scraped_structs

        last_player_id = data[-1]["player_id"]
        await update_latest_player_id(async_session, player_id=last_player_id)

        if len(data) < Settings().LIMIT:
            logger.debug("DONE")
            break

    await player_sc_producer.stop()


async def run_async():
    await main()


def run():
    asyncio.run(run_async())


if __name__ == "__main__":
    run()
