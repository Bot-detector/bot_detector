import asyncio
import logging

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
from bot_detector.event_queue.structs import DataToPredictStruct, ScrapedStruct
from bot_detector.ml_api import InputData, MLApiClient, Prediction
from bot_detector.structs import PredictionCreate
from bot_detector.worker import Worker, WorkerRunner
from bot_detector.worker_ml.settings import Settings
from bot_detector.worker_ml.settings import Settings as MLSettings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


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


async def insert_prediction_results(
    session_factory: async_sessionmaker[AsyncSession],
    predictions: list[PredictionCreate],
) -> None:
    pred_repo = PredictionRepo()
    pred_latest_repo = PredictionLatestRepo()
    async with session_factory() as session:
        await pred_repo.insert(session, predictions)
        await pred_latest_repo.insert(session, predictions)


class PlayerScrapedWorker(Worker[ScrapedStruct]):
    def __init__(
        self,
        api: MLApiClient,
        model_name: str,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._api = api
        self._model_name = model_name
        self._session_factory = session_factory

    async def handle(self, batch: list[ScrapedStruct]) -> None:
        logger.info(f"Consumed {len(batch)} records")

        parsed_data = [transform_scraped_struct(b) for b in batch]
        parsed_data = [p for p in parsed_data if p is not None]
        input_data = [p[1] for p in parsed_data]

        if not input_data:
            logger.info("No valid highscore data to process. (input_data is empty)")
            return

        predictions = await predict(
            api=self._api,
            model_name=self._model_name,
            input_data=input_data,
        )
        combined_predictions = [
            transform_prediction(
                player_id=player.player_data.id,
                prediction=pred,
                model_name=self._model_name,
            )
            for (player, _), pred in zip(parsed_data, predictions)
        ]

        await insert_prediction_results(
            session_factory=self._session_factory,
            predictions=combined_predictions,
        )


class DataToPredictWorker(Worker[DataToPredictStruct]):
    def __init__(
        self,
        api: MLApiClient,
        model_name: str,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._api = api
        self._model_name = model_name
        self._session_factory = session_factory

    async def handle(self, batch: list[DataToPredictStruct]) -> None:
        logger.info(f"Consumed {len(batch)} records")

        if not batch:
            logger.info("No highscore data to process.")
            return

        _input_data = [transform_data_to_predict_struct(d) for d in batch]

        _predictions = await predict(
            api=self._api,
            model_name=self._model_name,
            input_data=_input_data,
        )

        _predictions = [
            transform_prediction(
                player_id=b.player_id,
                prediction=pred,
                model_name=self._model_name,
            )
            for b, pred in zip(batch, _predictions)
        ]

        await insert_prediction_results(
            session_factory=self._session_factory,
            predictions=_predictions,
        )


async def main():
    session_factory, engine = get_session_factory(SETTINGS=DBSettings())

    http_session = aiohttp.ClientSession()
    api = MLApiClient(base_url=MLSettings().BASE_URL, session=http_session)

    tasks = []
    if Settings().CONSUME_PLAYER_SCRAPED:
        ps_worker = PlayerScrapedWorker(
            api=api,
            model_name=MLSettings().MODEL_NAME,
            session_factory=session_factory,
        )
        ps_runner = WorkerRunner(
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
            model=ScrapedStruct,
            worker=ps_worker,
            batch_size=MLSettings().MAX_MESSAGES,
            empty_batch_sleep=15.0,
            error_sleep=15.0,
        )
        tasks.append(asyncio.create_task(ps_runner.run()))

    if Settings().CONSUME_DATA_TO_PREDICT:
        dtp_worker = DataToPredictWorker(
            api=api,
            model_name=MLSettings().MODEL_NAME,
            session_factory=session_factory,
        )
        dtp_runner = WorkerRunner(
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
            model=DataToPredictStruct,
            worker=dtp_worker,
            batch_size=Settings().MAX_MESSAGES,
            empty_batch_sleep=15.0,
            error_sleep=15.0,
        )
        tasks.append(asyncio.create_task(dtp_runner.run()))

    await asyncio.gather(*tasks)

    await http_session.close()
    await engine.dispose()


async def run_async():
    await main()


def run():
    asyncio.run(run_async())


if __name__ == "__main__":
    run()
