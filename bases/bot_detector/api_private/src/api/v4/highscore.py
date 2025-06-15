import logging
from collections import defaultdict
from datetime import datetime

from bot_detector.api_private.src.app.repositories import ScraperDataRepo
from bot_detector.api_private.src.app.views.response import (
    ActivityView,
    ScraperDataView,
    SkillView,
)
from bot_detector.api_private.src.core.fastapi.dependencies.session import (
    get_session,
)
from bot_detector.database.repositories.hiscore import HighscoreDataLatestRepo
from bot_detector.structs import HighscoreDataLatestStruct
from fastapi import APIRouter, Depends, Query

logger = logging.getLogger(__name__)

router = APIRouter()


def convert_latest_struct_to_scraper_data_view(
    records: list[HighscoreDataLatestStruct],
) -> list[ScraperDataView]:
    return [
        ScraperDataView(
            created_at=record.created_at
            or datetime.combine(record.scrape_date, datetime.min.time()),
            record_date=record.scrape_date,
            scraper_id=record.player_id,
            player_id=record.player_id,
            player_name=record.player_name or "Unknown",
            skills=[
                SkillView(skill_name=k, skill_value=v)
                for k, v in (record.skills or {}).items()
            ],
            activities=[
                ActivityView(activity_name=k, activity_value=v)
                for k, v in (record.activities or {}).items()
            ],
        )
        for record in records
    ]


@router.get("/highscore/latest", response_model=list[ScraperDataView])
async def get_highscore_latest(
    player_id: int,
    label_id: int = None,
    many: bool = False,
    limit: int = Query(default=10, ge=0, le=10_000),
    session=Depends(get_session),
):
    repo = HighscoreDataLatestRepo()
    if many:
        rows = await repo.select_highscore_list(session, player_id, label_id, limit)
    else:
        row = await repo.select_highscore(session, player_id, label_id)
        rows = [row] if row else []
    return convert_latest_struct_to_scraper_data_view(rows)
