import asyncio
import logging
import traceback

import aiohttp
from bot_detector.database import Settings as DBSettings
from bot_detector.database import get_session_factory
from bot_detector.database.prediction import PredictionLatestRepo, PredictionRepo
from bot_detector.event_queue.adapters.kafka import (
    KafkaConfig,
    KafkaConsumerConfig,
    KafkaProducerConfig,
    KafkaSettings,
)
from bot_detector.event_queue.core import Queue
from bot_detector.event_queue.factory import QueueFactory
from bot_detector.event_queue.structs import DataToPredictStruct, ScrapedStruct
from bot_detector.ml_api import InputData, MLApiClient, Prediction
from bot_detector.structs import PredictionCreate
from bot_detector.worker_ml.settings import Settings
from bot_detector.worker_ml.settings import Settings as MLSettings
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


def transform_prediction(
    player_id: int,
    prediction: Prediction,
    model_name: str,
) -> PredictionCreate:
    _pred_dict: dict[str, float] = prediction.model_dump()
    _max_prob_key = max(_pred_dict, key=_pred_dict.get)  # type: ignore
    _confidence = round(_pred_dict[_max_prob_key], 4)
    _predictions = {k: round(v, 4) for k, v in prediction.model_dump().items()}

    return PredictionCreate(
        model_name=model_name,
        player_id=player_id,
        prediction=_max_prob_key,
        confidence=_confidence,
        predictions=_predictions,
    )


def transform_scraped_struct(
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


async def predict(
    api: MLApiClient,
    model_name: str,
    input_data: list[InputData],
) -> list[Prediction]:
    predictions = await api.predict(
        model_name=model_name,
        data=[d.model_dump() for d in input_data],
    )
    return [Prediction.model_validate(p) for p in predictions.prediction]


def transform_data_to_predict_struct(data: DataToPredictStruct) -> InputData:
    return InputData.model_validate(data.data.model_dump())


async def consume_data_to_predict(
    max_messages: int,
    data_to_predict_queue: Queue[DataToPredictStruct],
    api: MLApiClient,
    session_factory: async_sessionmaker[AsyncSession],
    model_name: str = "multi_model_v1",
):
    while True:
        _batch = await data_to_predict_queue.get_many(count=max_messages)

        if isinstance(_batch, Exception):
            raise _batch

        logger.info(f"Consumed {len(_batch)} records")

        if not _batch:
            logger.info("No highscore data to process.")
            await asyncio.sleep(15)
            continue

        _input_data = [transform_data_to_predict_struct(d) for d in _batch]

        # external network call
        try:
            _predictions = await predict(
                api=api,
                model_name=model_name,
                input_data=_input_data,
            )
        except Exception as e:
            logger.error(
                {
                    "model": model_name,
                    "input_data": _input_data[:3],
                    "error": str(e),
                }
            )
            put_result = await data_to_predict_queue.put(_batch)
            if isinstance(put_result, Exception):
                logger.error(
                    {
                        "error": "failed to requeue consumed records",
                        "reason": str(put_result),
                    }
                )
                await asyncio.sleep(15)
                continue
            await data_to_predict_queue.commit()
            await asyncio.sleep(15)
            continue

        _predictions = [
            transform_prediction(
                player_id=b.player_id,
                prediction=pred,
                model_name=model_name,
            )
            for b, pred in zip(_batch, _predictions)
        ]

        # database call
        try:
            await insert_prediction_results(
                session_factory=session_factory,
                predictions=_predictions,
            )
        except Exception as e:
            logger.error(
                {
                    "_predictions": _predictions[:3],
                    "error": str(e),
                }
            )
            put_result = await data_to_predict_queue.put(_batch)
            if isinstance(put_result, Exception):
                logger.error(
                    {
                        "error": "failed to requeue consumed records",
                        "reason": str(put_result),
                    }
                )
                await asyncio.sleep(15)
                continue
            await data_to_predict_queue.commit()
            await asyncio.sleep(15)
            continue
        await data_to_predict_queue.commit()


async def consume_player_scraped(
    max_messages: int,
    player_sc_queue: Queue[ScrapedStruct],
    api: MLApiClient,
    session_factory: async_sessionmaker[AsyncSession],
    model_name: str = "multi_model_v1",
):
    while True:
        batch = []
        try:
            batch = await player_sc_queue.get_many(count=max_messages)
            if isinstance(batch, Exception):
                logger.error(f"Errors during consumption: {batch}")
                raise batch

            logger.info(f"Consumed {len(batch)} records")

            if not batch:
                logger.info("No highscore data to process.")
                await asyncio.sleep(15)
                continue

            # send to ml model for inference
            parsed_data = [transform_scraped_struct(b) for b in batch]
            parsed_data = [p for p in parsed_data if p is not None]
            input_data = [p[1] for p in parsed_data]

            if not input_data:
                logger.info("No valid highscore data to process. (input_data is empty)")
                await player_sc_queue.commit()
                continue

            try:
                predictions = await predict(
                    api=api,
                    model_name=model_name,
                    input_data=input_data,
                )
                combined_predictions = [
                    transform_prediction(
                        player_id=player.player_data.id,
                        prediction=pred,
                        model_name=model_name,
                    )
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
                put_result = await player_sc_queue.put(batch)
                if isinstance(put_result, Exception):
                    logger.error(
                        {
                            "error": "failed to requeue consumed records",
                            "reason": str(put_result),
                        }
                    )
                    await asyncio.sleep(15)
                    continue
                await player_sc_queue.commit()
                await asyncio.sleep(15)
                continue

            # insert prediction results into mysql
            await insert_prediction_results(
                session_factory=session_factory,
                predictions=combined_predictions,
            )
            await player_sc_queue.commit()
        except Exception as e:
            logger.error(f"Error consuming scrapes: {e}")
            logger.debug(f"Traceback: \n{traceback.format_exc()}")
            if not isinstance(batch, Exception):
                put_result = await player_sc_queue.put(batch)
                if isinstance(put_result, Exception):
                    logger.error(
                        {
                            "error": "failed to requeue consumed records",
                            "reason": str(put_result),
                        }
                    )
                    await asyncio.sleep(15)
                    continue
                await player_sc_queue.commit()
            await asyncio.sleep(15)


async def main_player_scraped(
    api: MLApiClient, session_factory: async_sessionmaker[AsyncSession]
) -> tuple[asyncio.Task, Queue]:
    player_sc_queue = QueueFactory.create_queue(
        model=ScrapedStruct,
        queue_type="queue",
        backend_type="kafka",
        config=KafkaConfig(
            topic="players.scraped",
            bootstrap_servers=KafkaSettings().bootstrap_servers,
            producer=True,
            consumer=True,
            producer_config=KafkaProducerConfig(partition_key_fn=None),
            consumer_config=KafkaConsumerConfig(
                group_id="ml_worker",
                consume_timeout_ms=MLSettings().MAX_INTERVAL_MS,
            ),
        ),
    )
    if isinstance(player_sc_queue, Exception):
        raise player_sc_queue

    assert isinstance(player_sc_queue, Queue)

    await player_sc_queue.start()

    task = asyncio.create_task(
        consume_player_scraped(
            max_messages=MLSettings().MAX_MESSAGES,
            player_sc_queue=player_sc_queue,
            api=api,
            session_factory=session_factory,  # type: ignore
            model_name=MLSettings().MODEL_NAME,
        )
    )
    return task, player_sc_queue


async def main_data_to_predict(
    api: MLApiClient, session_factory: async_sessionmaker[AsyncSession]
) -> tuple[asyncio.Task, Queue]:
    data_to_predict_queue = QueueFactory.create_queue(
        model=DataToPredictStruct,
        queue_type="queue",
        backend_type="kafka",
        config=KafkaConfig(
            topic="data.to_predict",
            bootstrap_servers=KafkaSettings().bootstrap_servers,
            producer=True,
            consumer=True,
            producer_config=KafkaProducerConfig(partition_key_fn=None),
            consumer_config=KafkaConsumerConfig(
                group_id="ml_worker",
                consume_timeout_ms=Settings().MAX_INTERVAL_MS,
            ),
        ),
    )
    if isinstance(data_to_predict_queue, Exception):
        raise data_to_predict_queue
    assert isinstance(data_to_predict_queue, Queue)
    await data_to_predict_queue.start()

    task = asyncio.create_task(
        consume_data_to_predict(
            max_messages=Settings().MAX_MESSAGES,
            data_to_predict_queue=data_to_predict_queue,
            api=api,
            session_factory=session_factory,  # type: ignore
            model_name=Settings().MODEL_NAME,
        )
    )
    return task, data_to_predict_queue


async def main():
    ## database
    session_factory, engine = get_session_factory(SETTINGS=DBSettings())

    ## api client
    http_session = aiohttp.ClientSession()
    api = MLApiClient(base_url=MLSettings().BASE_URL, session=http_session)

    tasks = []
    if Settings().CONSUME_PLAYER_SCRAPED:
        task_ps, player_sc_queue = await main_player_scraped(
            api=api,
            session_factory=session_factory,
        )
        tasks.append(task_ps)

    if Settings().CONSUME_DATA_TO_PREDICT:
        task_dtp, data_to_predict_queue = await main_data_to_predict(
            api=api,
            session_factory=session_factory,
        )
        tasks.append(task_dtp)
    await asyncio.gather(*tasks)

    if Settings().CONSUME_PLAYER_SCRAPED:
        await player_sc_queue.stop()

    if Settings().CONSUME_DATA_TO_PREDICT:
        await data_to_predict_queue.stop()

    await http_session.close()
    await engine.dispose()


async def run_async():
    await main()


def run():
    asyncio.run(run_async())


if __name__ == "__main__":
    run()
