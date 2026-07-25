import logging
from typing import cast

import sqlalchemy as sqla
from sqlalchemy import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


def _insert_archive() -> sqla.TextClause:
    """Copy a banned player's report/location/gear data into report_archive.

    Denormalizes the report -> sighting/location/gear join into a single row
    keyed on (reported_id, reported_at). INSERT IGNORE makes it idempotent:
    re-delivered events and backfill re-runs do not duplicate rows.
    """
    return sqla.text(
        """
        INSERT IGNORE INTO report_archive (
            reported_id,
            world_number,
            on_members_world,
            on_pvp_world,
            reported_at,
            region_id,
            x_coord,
            y_coord,
            z_coord,
            equip_head_id,
            equip_amulet_id,
            equip_torso_id,
            equip_legs_id,
            equip_boots_id,
            equip_cape_id,
            equip_hands_id,
            equip_weapon_id,
            equip_shield_id
        )
        SELECT
            rs.reported_id,
            r.world_number,
            r.on_members_world,
            r.on_pvp_world,
            r.reported_at,
            r.region_id,
            rl.x_coord,
            rl.y_coord,
            rl.z_coord,
            rg.equip_head_id,
            rg.equip_amulet_id,
            rg.equip_torso_id,
            rg.equip_legs_id,
            rg.equip_boots_id,
            rg.equip_cape_id,
            rg.equip_hands_id,
            rg.equip_weapon_id,
            rg.equip_shield_id
        FROM report r
        JOIN report_sighting rs ON rs.report_sighting_id = r.report_sighting_id
        JOIN report_location rl ON rl.report_location_id = r.report_location_id
        JOIN report_gear rg ON rg.report_gear_id = r.report_gear_id
        WHERE rs.reported_id = :reported_id
        """
    )


async def migrate_banned_player_reports(
    session_factory: async_sessionmaker[AsyncSession],
    reported_id: int,
) -> int:
    """Copy a banned player's location history into report_archive.

    Copy semantics: source rows in report are left untouched. The prune job
    reclaims them later per the age window. Safe to call repeatedly thanks to
    the (reported_id, reported_at) natural key + INSERT IGNORE.

    Args:
        session_factory: SQLAlchemy async session factory.
        reported_id: The banned player (Players.label_jagex = 2) whose reports
            should be archived.

    Returns:
        Number of report_archive rows inserted by this call (0 on a re-run for
        already-archived data).
    """
    async with session_factory() as session, session.begin():
        result = await session.execute(
            _insert_archive(),
            params={"reported_id": reported_id},
        )
        inserted = cast(CursorResult, result).rowcount

    logger.info(
        f"migrate_banned_player_reports: archived {inserted} rows for reported_id={reported_id}"
    )
    return inserted
