import logging

from fastapi import APIRouter, Depends, Query

from src.app.repositories import PlayerActivityRepo, PlayerSkillsRepo, ScraperDataRepo
from src.app.views.response.highscore import PlayerHiscoreData

# from src.app.repositories.highscore import HighscoreRepo
from src.core.fastapi.dependencies.session import get_session

logger = logging.getLogger(__name__)


router = APIRouter()


# @router.get("/highscore/latest", response_model=list[PlayerHiscoreData])
# async def get_highscore_latest(
#     player_id: int,
#     label_id: int = None,
#     many: bool = False,
#     limit: int = Query(default=10, ge=0, le=10_000),
#     session=Depends(get_session),
# ):
#     repo = HighscoreRepo(session=session)
#     data: list[dict] = await repo.select(
#         player_id=player_id, label_id=label_id, many=many, limit=limit
#     )

#     data = [{k: v for k, v in d.items() if v} for d in data]
#     return [PlayerHiscoreData(**d).model_dump(mode="json") for d in data]


@router.get("/highscore/latest")
async def get_highscore_latest_v2(
    player_id: int,
    player_name: str = None,
    label_id: int = None,
    many: bool = False,
    limit: int = Query(default=10, ge=0, le=10_000),
    session=Depends(get_session),
):
    repo = ScraperDataRepo(session=session)
    repo_skills = PlayerSkillsRepo(session=session)
    repo_activities = PlayerActivityRepo(session=session)

    data = await repo.select(
        player_name=player_name,
        player_id=player_id,
        label_id=label_id,
        many=many,
        limit=limit,
        history=False,
    )

    logger.info(data[0])
    for d in data:
        scraper_id = d.pop("scraper_id")
        d["Player_id"] = d.pop("player_id")
        d["id"] = scraper_id
        d["timestamp"] = d.pop("created_at")
        d["ts_date"] = d.pop("record_date")

        skills = await repo_skills.select(scraper_id=scraper_id)
        activities = await repo_activities.select(scraper_id=scraper_id)

        for skill in skills:
            d[skill.get("skill_name")] = skill.get("skill_value")

        for activity in activities:
            d[activity.get("activity_name")] = activity.get("activity_value")

    data = [{k: v for k, v in d.items() if v} for d in data]
    return [PlayerHiscoreData(**d).model_dump(mode="json") for d in data]
