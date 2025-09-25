# consumes data from kafka
## TOPIC: players.scraped
# does inference with ml model
## POST /v1/models/{model_name}/predict
# inserts data into mysql
import asyncio
import json
import logging
import traceback

import aiohttp
from bot_detector.kafka import Settings as KafkaSettings
from bot_detector.kafka.repositories import (
    RepoPlayerScrapedConsumer,
    RepoPlayerScrapedProducer,
)
from bot_detector.ml_api.core import MLApiClient
from bot_detector.ml_api.structs import InputData
from bot_detector.worker_ml.settings import Settings

logger = logging.getLogger(__name__)


async def consume_many_task(
    max_messages: int,
    max_interval_ms: int,
    player_sc_consumer: RepoPlayerScrapedConsumer,
    player_sc_producer: RepoPlayerScrapedProducer,
    api: MLApiClient,
):
    while True:
        try:
            batch, errors = await player_sc_consumer.consume_many(
                max_messages=max_messages,
                timeout_ms=max_interval_ms,
            )
            logger.info(f"Consumed {len(batch)} scrapes")
            if errors:
                logger.error(f"Errors during consumption: {errors}")

            if not batch:
                logger.info("No highscore data to process.")
                await asyncio.sleep(15)
                continue

            # send to ml model for inference
            parsed_data = []
            for b in batch:
                skills = b.highscore_data.skills or {}
                activities = b.highscore_data.activities or {}
                skills = {k.lower(): v for k, v in skills.items()}
                activities = {k.lower(): v for k, v in activities.items()}
                _input = {**skills, **activities}
                assert sum(_input.values()) > 0, "No skill or activity data"
                _input = InputData(**_input).model_dump()
                parsed_data.append(_input)

            logger.debug(f"Parsed data for ML: {parsed_data}")
            try:
                responses = await api.predict(
                    model_name="multi_model_v1",
                    data=parsed_data,
                )
            except Exception as e:
                logger.error(f"Error during prediction: {e}")
                await asyncio.gather(
                    *[player_sc_producer.produce_one(b) for b in batch]
                )
                await asyncio.sleep(15)
            # insert prediction results into mysql
            logger.info(f"ML responses: {responses}")
            await player_sc_consumer.commit()
        except Exception as e:
            logger.error(f"Error consuming scrapes: {e}")
            logger.debug(f"Traceback: \n{traceback.format_exc()}")
            await asyncio.gather(*[player_sc_producer.produce_one(b) for b in batch])
            await asyncio.sleep(15)


async def main():
    ## consumer
    player_sc_consumer = RepoPlayerScrapedConsumer(
        bootstrap_servers=KafkaSettings().KAFKA_BOOTSTRAP_SERVERS,
        group_id="ml_worker",
    )
    ## producer
    player_sc_producer = RepoPlayerScrapedProducer(
        bootstrap_servers=KafkaSettings().KAFKA_BOOTSTRAP_SERVERS,
    )
    session = aiohttp.ClientSession()
    api = MLApiClient(base_url=Settings().BASE_URL, session=session)

    # start kafka producers and consumers
    await player_sc_consumer.start()
    await player_sc_producer.start()

    tasks = [
        asyncio.create_task(
            consume_many_task(
                max_messages=Settings().MAX_MESSAGES,
                max_interval_ms=Settings().MAX_INTERVAL_MS,
                player_sc_consumer=player_sc_consumer,
                player_sc_producer=player_sc_producer,
                api=api,
            )
        )
    ]
    await asyncio.gather(*tasks)
    await session.close()


if __name__ == "__main__":
    asyncio.run(main())
