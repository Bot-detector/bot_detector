USE playerdata;

CREATE TABLE Players (
  id INT PRIMARY KEY AUTO_INCREMENT,
  name TEXT,
  created_at TIMESTAMP,
  updated_at TIMESTAMP,
  possible_ban BOOLEAN,
  confirmed_ban BOOLEAN,
  confirmed_player BOOLEAN,
  label_id INTEGER,
  label_jagex INTEGER,
  ironman BOOLEAN,
  hardcore_ironman BOOLEAN,
  ultimate_ironman BOOLEAN,
  normalized_name TEXT,
  UNIQUE KEY `Unique_name` (`name`(50))
);

/*
-- V4
*/
CREATE TABLE `highscore_data` (
  `player_id` INT NOT NULL,
  `scrape_ts` DATETIME NOT NULL,
  `scrape_year` INT AS (YEAR(scrape_ts)) STORED,
  `scrape_week` INT AS (WEEK(scrape_ts, 3)) STORED,
  `skills` JSON DEFAULT NULL,
  `activities` JSON DEFAULT NULL,
  PRIMARY KEY (`player_id`, `scrape_year`, `scrape_week`)
) PARTITION BY HASH (`player_id`) PARTITIONS 10;