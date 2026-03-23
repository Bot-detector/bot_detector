CREATE DATABASE playerdata;

CREATE USER `report-worker`@`%` IDENTIFIED BY 'report_worker_pw';
CREATE USER `hiscore-worker`@`%` IDENTIFIED BY 'hiscore_worker_pw';
CREATE USER `ml-worker`@`%` IDENTIFIED BY 'ml_worker_pw';
CREATE USER `job-prune-hs`@`%` IDENTIFIED BY 'job_prune_hs_pw';
CREATE USER `job-hs-migration`@`%` IDENTIFIED BY 'job_hs_migration_pw';