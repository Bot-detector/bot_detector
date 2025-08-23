/*report-worker*/
GRANT CREATE TEMPORARY TABLES ON *.* TO `report-worker`@`%`;
GRANT SELECT, INSERT, UPDATE ON playerdata.Players TO `report-worker`@`%`;
-- GRANT SELECT ON playerdata.Reports TO `report-worker`@`%`;
-- GRANT INSERT ON playerdata.stgReports TO `report-worker`@`%`;

GRANT SELECT, INSERT ON playerdata.report_sighting TO `report-worker`@`%`;
GRANT SELECT, INSERT ON playerdata.report_gear TO `report-worker`@`%`;
GRANT SELECT, INSERT ON playerdata.report_location TO `report-worker`@`%`;
GRANT SELECT, INSERT ON playerdata.report TO `report-worker`@`%`;

GRANT SELECT, INSERT, CREATE, DROP ON playerdata.temp_sighting TO `report-worker`@`%`;
GRANT SELECT, INSERT, CREATE, DROP ON playerdata.temp_gear TO `report-worker`@`%`;
GRANT SELECT, INSERT, CREATE, DROP ON playerdata.temp_location TO `report-worker`@`%`;
GRANT SELECT, INSERT, CREATE, DROP ON playerdata.temp_report TO `report-worker`@`%`;

/*job-prune-hs*/
GRANT CREATE TEMPORARY TABLES ON *.* TO `job-prune-hs`@`%`;
GRANT SELECT ON playerdata.Players TO `job-prune-hs`@`%`;
GRANT SELECT, DELETE ON playerdata.highscore_data_daily TO `job-prune-hs`@`%`;

GRANT SELECT, INSERT, CREATE, DROP ON playerdata.tmp_player_ids TO `job-prune-hs`@`%`;
/*job-hs-migration*/
GRANT SELECT, UPDATE ON playerdata.migration_hs_v3 TO `job-hs-migration`@`%`;
GRANT SELECT ON playerdata.Players TO `job-hs-migration`@`%`;
GRANT SELECT ON playerdata.scraper_data_v3 TO `job-hs-migration`@`%`;
GRANT SELECT ON playerdata.scraper_player_skill TO `job-hs-migration`@`%`;
GRANT SELECT ON playerdata.player_skill TO `job-hs-migration`@`%`;
GRANT SELECT ON playerdata.skill TO `job-hs-migration`@`%`;
GRANT SELECT ON playerdata.scraper_player_activity TO `job-hs-migration`@`%`;
GRANT SELECT ON playerdata.player_activity TO `job-hs-migration`@`%`;
GRANT SELECT ON playerdata.activity TO `job-hs-migration`@`%`;

FLUSH PRIVILEGES;
