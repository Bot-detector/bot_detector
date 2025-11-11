import asyncio
import logging
import traceback

import aiohttp
from bot_detector.database import Settings as DBSettings
from bot_detector.database import get_session_factory
from bot_detector.database.prediction import PredictionLatestRepo, PredictionRepo
from bot_detector.kafka import Settings as KafkaSettings
from bot_detector.kafka.repositories import (
    RepoPlayerScrapedConsumer,
    RepoPlayerScrapedProducer,
)
from bot_detector.ml_api.core import MLApiClient
from bot_detector.ml_api.structs import InputData, Prediction
from bot_detector.structs import PredictionCreate, ScrapedStruct
from bot_detector.worker_ml.settings import Settings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


async def insert_prediction_results(
    session_factory: async_sessionmaker[AsyncSession],
    predictions: list[PredictionCreate],
) -> None:
    pred_repo = PredictionRepo()
    pred_latest_repo = PredictionLatestRepo()
    async with session_factory() as session:
        await pred_repo.insert(session, predictions)
        await pred_latest_repo.insert(session, predictions)
    return


def create_prediction_create(
    player: ScrapedStruct, prediction: Prediction, model_name: str
) -> PredictionCreate:
    pred_dict: dict[str, float] = prediction.model_dump()
    max_prob_key = max(pred_dict, key=pred_dict.get)  # type: ignore

    return PredictionCreate(
        model_name=model_name,
        player_id=player.player_data.id,
        prediction=max_prob_key,
        confidence=pred_dict[max_prob_key],
        predictions=prediction.model_dump(),
    )


def create_parsed_input(
    player: ScrapedStruct,
) -> tuple[ScrapedStruct, InputData] | None:
    skills, activities = {}, {}

    if player.highscore_data:
        skills = player.highscore_data.skills or {}
        activities = player.highscore_data.activities or {}

    # normalize keys to lowercase (db has mixed casing)
    skills = {k.lower(): v for k, v in skills.items()}
    activities = {k.lower(): v for k, v in activities.items()}

    _input = {**skills, **activities}
    if sum(_input.values()) == 0:
        return None
    return player, InputData(**_input)


async def consume_many_task(
    max_messages: int,
    max_interval_ms: int,
    player_sc_consumer: RepoPlayerScrapedConsumer,
    player_sc_producer: RepoPlayerScrapedProducer,
    api: MLApiClient,
    session_factory: async_sessionmaker[AsyncSession],
    model_name: str = "multi_model_v1",
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
            parsed_data = [create_parsed_input(b) for b in batch]
            parsed_data = [p for p in parsed_data if p is not None]
            input_data = [p[1].model_dump() for p in parsed_data if p is not None]

            if not input_data:
                logger.info("No valid highscore data to process. (input_data is empty)")
                await player_sc_consumer.commit()
                continue

            try:
                predictions = await api.predict(
                    model_name=model_name,
                    data=input_data,
                )
                predictions = [
                    Prediction.model_validate(p) for p in predictions.prediction
                ]
                combined_predictions = [
                    create_prediction_create(player, pred, model_name=model_name)
                    for (player, _), pred in zip(parsed_data, predictions)
                ]
            except Exception as e:
                logger.error(
                    {
                        "model": model_name,
                        "input_data": input_data[:3],
                        "error": str(e),
                    }
                )
                await asyncio.gather(
                    *[player_sc_producer.produce_one(b) for b in batch]
                )
                await player_sc_consumer.commit()
                await asyncio.sleep(15)
                continue

            # insert prediction results into mysql
            await insert_prediction_results(
                session_factory=session_factory,
                predictions=combined_predictions,
            )
            await player_sc_consumer.commit()
        except Exception as e:
            logger.error(f"Error consuming scrapes: {e}")
            logger.debug(f"Traceback: \n{traceback.format_exc()}")
            await asyncio.gather(*[player_sc_producer.produce_one(b) for b in batch])
            await asyncio.sleep(15)


async def main():
    ## database
    session_factory, engine = get_session_factory(SETTINGS=DBSettings())
    ## kafka consumer
    player_sc_consumer = RepoPlayerScrapedConsumer(
        bootstrap_servers=KafkaSettings().KAFKA_BOOTSTRAP_SERVERS,
        group_id="ml_worker",
    )
    ## kafka producer
    player_sc_producer = RepoPlayerScrapedProducer(
        bootstrap_servers=KafkaSettings().KAFKA_BOOTSTRAP_SERVERS,
    )
    ## api client
    http_session = aiohttp.ClientSession()
    api = MLApiClient(base_url=Settings().BASE_URL, session=http_session)

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
                session_factory=session_factory,  # type: ignore
                model_name=Settings().MODEL_NAME,
            )
        )
    ]
    await asyncio.gather(*tasks)
    await player_sc_consumer.stop()
    await player_sc_producer.stop()
    await http_session.close()
    await engine.dispose()


async def run_async():
    await main()


def run():
    asyncio.run(run_async())


if __name__ == "__main__":
    run()
