import logging
from collections import defaultdict

from fastapi import APIRouter, Depends, Query

from bases.bot_detector.api_private.src.app.repositories import ScraperDataRepo
from bases.bot_detector.api_private.src.app.views.response import (
    ActivityView,
    ScraperDataView,
    SkillView,
)
from bases.bot_detector.api_private.src.core.fastapi.dependencies.session import (
    get_session,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def convert_to_scraper_data_view(result_list: list[dict]) -> list[ScraperDataView]:
    # Dictionary to hold grouped data by scraper_id
    scraper_data_map = defaultdict(lambda: {"skills": [], "activities": []})

    for row in result_list:
        scraper_id = row["scrape_id"]
        scraper_data = scraper_data_map[scraper_id]

        # Set shared attributes only once per scraper_id
        if "created_at" not in scraper_data:
            scraper_data["created_at"] = row["scrape_ts"]
            scraper_data["record_date"] = row["scrape_date"]
            scraper_data["scraper_id"] = scraper_id
            scraper_data["player_id"] = row["player_id"]
            scraper_data["player_name"] = row["player_name"]

        # Append to skills or activities based on hs_type
        if row["hs_type"] == "skill":
            scraper_data["skills"].append(
                SkillView(skill_name=row["hs_name"], skill_value=row["hs_value"])
            )
        elif row["hs_type"] == "activity":
            scraper_data["activities"].append(
                ActivityView(
                    activity_name=row["hs_name"], activity_value=row["hs_value"]
                )
            )

    # Convert the grouped data into ScraperDataView instances
    return [
        ScraperDataView(
            created_at=data["created_at"],
            record_date=data["record_date"],
            scraper_id=data["scraper_id"],
            player_id=data["player_id"],
            player_name=data["player_name"],
            skills=data["skills"],
            activities=data["activities"],
        )
        for data in scraper_data_map.values()
    ]


@router.get("/highscore/latest", response_model=list[ScraperDataView])
async def get_highscore_latest(
    player_id: int,
    label_id: int = None,
    many: bool = False,
    limit: int = Query(default=10, ge=0, le=10_000),
    session=Depends(get_session),
):
    repo = ScraperDataRepo(session=session)
    data = await repo.select_latest_scraper_data_v3(
        player_id=player_id,
        label_id=label_id,
        many=many,
        limit=limit,
    )
    return convert_to_scraper_data_view(result_list=data)
