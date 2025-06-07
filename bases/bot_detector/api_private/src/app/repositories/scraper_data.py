from sqlalchemy import func, literal, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from bases.bot_detector.api_private.src.core.database.models.player import Player
from bases.bot_detector.api_private.src.core.database.models.scraper_data_v3 import (
    Activity,
    PlayerActivity,
    PlayerSkill,
    ScraperDataV3,
    ScraperPlayerActivity,
    ScraperPlayerSkill,
    Skill,
)


class ScraperDataRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def select_latest_scraper_data_v3(
        self,
        player_id: int = None,
        label_id: int = None,
        many: bool = True,
        limit: int = 1000,
    ):
        # Aliases for tables
        SDV = aliased(ScraperDataV3)
        P = aliased(Player)

        # skill specific
        SPS = aliased(ScraperPlayerSkill)
        PS = aliased(PlayerSkill)
        S = aliased(Skill)

        # activity specific
        SPA = aliased(ScraperPlayerActivity)
        PA = aliased(PlayerActivity)
        A = aliased(Activity)

        # Subquery to get the latest scrape date for each player
        subquery = (
            select(func.max(SDV.scrape_date).label("max_scrape_date"), SDV.player_id)
            .join(P, SDV.player_id == P.id)
            .group_by(SDV.player_id)
        )

        if player_id:
            if many:
                subquery = subquery.where(P.id >= player_id)
            else:
                subquery = subquery.where(P.id == player_id)
        if label_id:
            subquery = subquery.where(P.label_id == label_id)

        subquery = subquery.limit(limit)
        subquery = subquery.subquery()

        # Skill query
        skill_query = (
            select(
                SDV.scrape_id,
                SDV.scrape_ts,
                SDV.scrape_date,
                SDV.player_id,
                P.name.label("player_name"),
                S.skill_id.label("hs_id"),
                S.skill_name.label("hs_name"),
                PS.skill_value.label("hs_value"),
                literal("skill").label("hs_type"),
            )
            .select_from(SDV)
            .join(
                subquery,
                (subquery.c.max_scrape_date == SDV.scrape_date)
                & (subquery.c.player_id == SDV.player_id),
            )
            .join(P, SDV.player_id == P.id)
            .join(SPS, SDV.scrape_id == SPS.scrape_id)
            .join(PS, SPS.player_skill_id == PS.player_skill_id)
            .join(S, PS.skill_id == S.skill_id)
        )

        # Activity query
        activity_query = (
            select(
                SDV.scrape_id,
                SDV.scrape_ts,
                SDV.scrape_date,
                SDV.player_id,
                P.name.label("player_name"),
                A.activity_id.label("hs_id"),
                A.activity_name.label("hs_name"),
                PA.activity_value.label("hs_value"),
                literal("activity").label("hs_type"),
            )
            .select_from(SDV)
            .join(
                subquery,
                (subquery.c.max_scrape_date == SDV.scrape_date)
                & (subquery.c.player_id == SDV.player_id),
            )
            .join(P, SDV.player_id == P.id)
            .join(SPA, SDV.scrape_id == SPA.scrape_id)
            .join(PA, SPA.player_activity_id == PA.player_activity_id)
            .join(A, PA.activity_id == A.activity_id)
        )

        # Combine skill and activity queries using union_all
        combined_query = union_all(skill_query, activity_query)

        # Wrap the combined_query in a new select statement to apply additional filters
        final_query = select(
            combined_query.c.scrape_id,
            combined_query.c.scrape_ts,
            combined_query.c.scrape_date,
            combined_query.c.player_id,
            combined_query.c.player_name,
            combined_query.c.hs_id,
            combined_query.c.hs_name,
            combined_query.c.hs_value,
            combined_query.c.hs_type,
        ).select_from(combined_query)

        # Execute the final query
        result = await self.session.execute(final_query)
        result_list = result.mappings().all()
        return result_list
