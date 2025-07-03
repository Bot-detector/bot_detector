CREATE DATABASE playerdata;

CREATE USER `report-worker`@`%` IDENTIFIED BY 'report_worker_pw';
CREATE USER `hiscore-worker`@`%` IDENTIFIED BY 'hiscore_worker_pw';