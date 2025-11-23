import logging
from datetime import datetime

import sqlalchemy as sqla
from bot_detector.structs import ParsedDetection
from sqlalchemy import TextClause
from sqlalchemy.ext.asyncio import AsyncSession

from .interface import ReportInterface

logger = logging.getLogger(__name__)


class ReportRepo(ReportInterface):
    def _parse_reports(self, reports: list[ParsedDetection]) -> list[dict]:
        _reports = []

        for report in reports:
            if not isinstance(report, ParsedDetection):
                logger.warning(
                    {
                        "msg": "invalid report",
                        "expected": "ParsedDetection",
                        "received": report.__class__,
                    }
                )
                continue
            # convert model to dict
            report_dict = report.model_dump()
            # flatten nested equiment
            equipment: dict = report_dict.pop("equipment", {})
            ## correct for NONE values
            equipment = {k: v for k, v in equipment.items() if v is not None}
            ## correct for item bug
            equipment = {k: 0 if v > 32767 else v for k, v in equipment.items()}

            report_dict.update(equipment)

            # epoch timestamp to datetime value
            ts = report_dict.pop("ts")
            ## assume ts is in ms if its very large and convert to seconds
            ts = ts / 1000 if ts > 10**10 else ts
            human_time = datetime.fromtimestamp(ts)
            report_dict["timestamp"] = human_time

            # add to reports
            _reports.append(report_dict)
        return _reports

    def _create_temp_report(self) -> TextClause:
        return sqla.text(
            """
            CREATE TEMPORARY TABLE temp_report (
                /*sighting*/
                reporting_id INT,
                reported_id INT,
                manual_detect TINYINT DEFAULT 0,
                /*gear*/
                `equip_head_id` SMALLINT,
                `equip_amulet_id` SMALLINT,
                `equip_torso_id` SMALLINT,
                `equip_legs_id` SMALLINT,
                `equip_boots_id` SMALLINT,
                `equip_cape_id` SMALLINT,
                `equip_hands_id` SMALLINT,
                `equip_weapon_id` SMALLINT,
                `equip_shield_id` SMALLINT,
                /*location*/
                `region_id` MEDIUMINT UNSIGNED NOT NULL,
                `x_coord` MEDIUMINT UNSIGNED NOT NULL,
                `y_coord` MEDIUMINT UNSIGNED NOT NULL,
                `z_coord` MEDIUMINT UNSIGNED NOT NULL,
                /*report*/
                `reported_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
                `on_members_world` TINYINT DEFAULT NULL,
                `on_pvp_world` TINYINT DEFAULT NULL,
                `world_number` SMALLINT UNSIGNED DEFAULT NULL
            ) ENGINE=MEMORY;
        """
        )

    def _insert_temp_report(self) -> TextClause:
        return sqla.text(
            """
            INSERT INTO temp_report (
                /*sighting*/
                reporting_id,
                reported_id,
                manual_detect,
                /*gear*/
                equip_head_id,
                equip_amulet_id,
                equip_torso_id,
                equip_legs_id,
                equip_boots_id,
                equip_cape_id,
                equip_hands_id,
                equip_weapon_id,
                equip_shield_id,
                /*location*/
                region_id,
                x_coord,
                y_coord,
                z_coord,
                /*report*/
                reported_at,
                on_members_world,
                on_pvp_world,
                world_number
            )
            VALUES (
                :reporter_id,
                :reported_id,
                :manual_detect,
                :equip_head_id,
                :equip_amulet_id,
                :equip_torso_id,
                :equip_legs_id,
                :equip_boots_id,
                :equip_cape_id,
                :equip_hands_id,
                :equip_weapon_id,
                :equip_shield_id,
                :region_id,
                :x_coord,
                :y_coord,
                :z_coord,
                :timestamp,
                :on_members_world,
                :on_pvp_world,
                :world_number
            );
        """
        )

    def _insert_sighting(self) -> TextClause:
        return sqla.text(
            """
            INSERT INTO report_sighting (reporting_id, reported_id, manual_detect)
            SELECT DISTINCT tr.reporting_id, tr.reported_id, tr.manual_detect FROM temp_report tr
            WHERE NOT EXISTS (
                SELECT 1 FROM report_sighting rs
                WHERE 1
                    AND tr.reporting_id = rs.reporting_id
                    AND tr.reported_id = rs.reported_id
                    AND tr.manual_detect = rs.manual_detect
            );
        """
        )

    def _insert_gear(self) -> TextClause:
        return sqla.text(
            """
            INSERT INTO report_gear (
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
            SELECT DISTINCT
                tr.equip_head_id,
                tr.equip_amulet_id,
                tr.equip_torso_id,
                tr.equip_legs_id,
                tr.equip_boots_id,
                tr.equip_cape_id,
                tr.equip_hands_id,
                tr.equip_weapon_id,
                tr.equip_shield_id
            FROM temp_report tr
            WHERE NOT EXISTS (
                SELECT
                    1
                FROM report_gear rg
                WHERE tr.equip_head_id = rg.equip_head_id
                AND tr.equip_amulet_id = rg.equip_amulet_id
                AND tr.equip_torso_id = rg.equip_torso_id
                AND tr.equip_legs_id = rg.equip_legs_id
                AND tr.equip_boots_id = rg.equip_boots_id
                AND tr.equip_cape_id = rg.equip_cape_id
                AND tr.equip_hands_id = rg.equip_hands_id
                AND tr.equip_weapon_id = rg.equip_weapon_id
                AND tr.equip_shield_id = rg.equip_shield_id
            );
        """
        )

    def _insert_location(self) -> TextClause:
        return sqla.text(
            """
            INSERT INTO report_location (region_id, x_coord, y_coord, z_coord)
            SELECT DISTINCT tr.region_id, tr.x_coord, tr.y_coord, tr.z_coord FROM temp_report tr
            WHERE NOT EXISTS (
                SELECT 1 FROM report_location rl
                WHERE 1
                    AND tr.region_id = rl.region_id
                    AND tr.x_coord = rl.x_coord
                    AND tr.y_coord = rl.y_coord
                    AND tr.z_coord = rl.z_coord
            );
            """
        )

    def _insert_report(self) -> TextClause:
        return sqla.text(
            """
                INSERT IGNORE INTO report (
                    report_sighting_id,
                    report_location_id,
                    report_gear_id,
                    reported_at,
                    on_members_world,
                    on_pvp_world,
                    world_number,
                    region_id
                )
                SELECT DISTINCT
                    rs.report_sighting_id,
                    rl.report_location_id,
                    rg.report_gear_id,
                    tr.reported_at,
                    tr.on_members_world,
                    tr.on_pvp_world,
                    tr.world_number,
                    tr.region_id
                FROM temp_report tr
                JOIN report_sighting rs
                    ON rs.reporting_id = tr.reporting_id
                    AND rs.reported_id = tr.reported_id
                JOIN report_location rl
                    ON rl.region_id = tr.region_id
                    AND rl.x_coord = tr.x_coord
                    AND rl.y_coord = tr.y_coord
                    AND rl.z_coord = tr.z_coord
                JOIN report_gear rg
                    ON rg.equip_head_id = tr.equip_head_id
                    AND rg.equip_amulet_id = tr.equip_amulet_id
                    AND rg.equip_torso_id = tr.equip_torso_id
                    AND rg.equip_legs_id = tr.equip_legs_id
                    AND rg.equip_boots_id = tr.equip_boots_id
                    AND rg.equip_cape_id = tr.equip_cape_id
                    AND rg.equip_hands_id = tr.equip_hands_id
                    AND rg.equip_weapon_id = tr.equip_weapon_id
                    AND rg.equip_shield_id = tr.equip_shield_id
                WHERE NOT EXISTS (
                    SELECT 1 FROM report rp
                    WHERE 1
                        AND rs.report_sighting_id = rp.report_sighting_id
                        AND rl.report_location_id = rp.report_location_id
                        AND tr.region_id = rp.region_id
                )
                ;
            """
        )

    async def insert(
        self, async_session: AsyncSession, reports: list[ParsedDetection]
    ) -> None:
        _reports = self._parse_reports(reports=reports)
        sql_create_temp_report = self._create_temp_report()
        sql_insert_temp_report = self._insert_temp_report()
        sql_insert_sighting = self._insert_sighting()
        sql_insert_gear = self._insert_gear()
        sql_insert_location = self._insert_location()
        sql_insert_report = self._insert_report()

        await async_session.execute(sqla.text("DROP TABLE IF EXISTS temp_report;"))
        await async_session.execute(sql_create_temp_report)
        await async_session.execute(sql_insert_temp_report, params=_reports)
        await async_session.execute(sql_insert_sighting)
        await async_session.execute(sql_insert_gear)
        await async_session.execute(sql_insert_location)
        await async_session.execute(sql_insert_report)
        await async_session.execute(sqla.text("DROP TABLE IF EXISTS temp_report;"))

    async def select(self, async_session: AsyncSession) -> None:
        raise NotImplementedError()

    async def update(self, async_session: AsyncSession) -> None:
        raise NotImplementedError()

    async def delete(self, async_session: AsyncSession) -> None:
        raise NotImplementedError()
