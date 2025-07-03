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
FLUSH PRIVILEGES;