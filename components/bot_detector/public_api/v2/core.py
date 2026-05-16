import logging

import aiohttp
import orjson
from bot_detector.public_api._retry import RetryableError, retry
from bot_detector.public_api.v2.structs import (
    Detection,
    FeedbackExportResponse,
    FeedbackInput,
    FeedbackScoreResponse,
    LabelResponse,
    Ok,
    PredictionResponse,
    ReportScoreResponse,
)
from bot_detector.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class PublicApiClient:
    DEFAULT_BASE_URL = "https://api.prd.osrsbotdetector.com"

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str | None = None,
        limiter: RateLimiter | None = None,
        token: str | None = None,
        api_user: str | None = None,
    ):
        self.session = session
        self.base_url = base_url or self.DEFAULT_BASE_URL
        self.limiter = limiter or RateLimiter()
        self.token = token
        self.api_user = api_user

    @retry(max_attempts=3)
    async def get_report_score(self, names: list[str]) -> list[ReportScoreResponse]:
        await self.limiter.check()
        async with self.session.get(
            self.base_url + "/v2/player/report/score",
            params={"name": names},
        ) as res:
            res.raise_for_status()
            data = orjson.loads(await res.read())
            return [ReportScoreResponse(**r) for r in data]

    @retry(max_attempts=3)
    async def get_feedback_score(self, names: list[str]) -> list[FeedbackScoreResponse]:
        await self.limiter.check()
        async with self.session.get(
            self.base_url + "/v2/player/feedback/score",
            params={"name": names},
        ) as res:
            res.raise_for_status()
            data = orjson.loads(await res.read())
            return [FeedbackScoreResponse(**r) for r in data]

    @retry(max_attempts=3)
    async def get_prediction(
        self, names: list[str], breakdown: bool = True
    ) -> list[PredictionResponse] | None:
        await self.limiter.check()
        async with self.session.get(
            self.base_url + "/v2/player/prediction",
            params={"name": names, "breakdown": str(breakdown)},
        ) as res:
            if res.status == 404:
                return None
            if res.status >= 500:
                raise RetryableError(f"Server error: {res.status}")
            res.raise_for_status()
            data = orjson.loads(await res.read())
            return [PredictionResponse(**r) for r in data]

    @retry(max_attempts=3)
    async def post_reports(self, detections: list[Detection]) -> Ok:
        await self.limiter.check()
        async with self.session.post(
            self.base_url + "/v2/report",
            data=orjson.dumps([d.model_dump() for d in detections]),
            headers={"Content-Type": "application/json"},
        ) as res:
            res.raise_for_status()
            return Ok(**orjson.loads(await res.read()))

    @retry(max_attempts=3)
    async def post_feedback(self, feedback: FeedbackInput) -> Ok:
        await self.limiter.check()
        async with self.session.post(
            self.base_url + "/v2/feedback",
            data=orjson.dumps(feedback.model_dump()),
            headers={"Content-Type": "application/json"},
        ) as res:
            res.raise_for_status()
            return Ok(**orjson.loads(await res.read()))

    @retry(max_attempts=3)
    async def get_labels(self) -> list[LabelResponse]:
        await self.limiter.check()
        async with self.session.get(
            self.base_url + "/v2/labels",
        ) as res:
            res.raise_for_status()
            data = orjson.loads(await res.read())
            return [LabelResponse(**r) for r in data]

    @retry(max_attempts=3)
    async def get_label_by_id(self, label_id: int) -> LabelResponse | None:
        await self.limiter.check()
        async with self.session.get(
            self.base_url + f"/v2/labels/{label_id}",
        ) as res:
            res.raise_for_status()
            data = orjson.loads(await res.read())
            if data is None:
                return None
            return LabelResponse(**data)

    @retry(max_attempts=3)
    async def get_feedback_export(
        self, player_name: str
    ) -> FeedbackExportResponse | None:
        await self.limiter.check()
        auth = None
        if self.api_user and self.token:
            auth = aiohttp.BasicAuth(self.api_user, self.token)
        async with self.session.get(
            self.base_url + "/v2/feedback/export",
            params={"player_name": player_name},
            auth=auth,
        ) as res:
            if res.status == 204:
                return None
            if res.status == 404:
                return None
            if res.status == 401:
                logger.error(f"Unauthorized feedback export request for {player_name}")
                return None
            res.raise_for_status()
            data = orjson.loads(await res.read())
            return FeedbackExportResponse(**data)
