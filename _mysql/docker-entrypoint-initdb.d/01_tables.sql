USE playerdata;
CREATE TABLE Players (
  id INT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(50),
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
  normalized_name VARCHAR(50),
  UNIQUE KEY `Unique_name` (`name`)
);

CREATE TABLE player (
  player_id INT UNSIGNED NOT NULL AUTO_INCREMENT,
  player_name VARCHAR(50) NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (player_id),
  UNIQUE KEY `Unique_name` (`player_name`)
);

CREATE TABLE player_attributes (
  player_id INT UNSIGNED NOT NULL,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  possible_ban BOOLEAN,
  confirmed_ban BOOLEAN,
  confirmed_player BOOLEAN,
  label_id INTEGER,
  label_jagex INTEGER,
  PRIMARY KEY (player_id)
);

CREATE TABLE player_attributes_history (
  player_id INT UNSIGNED NOT NULL,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  possible_ban BOOLEAN,
  confirmed_ban BOOLEAN,
  confirmed_player BOOLEAN,
  label_id INTEGER,
  label_jagex INTEGER,
  PRIMARY KEY (player_id, updated_at) 
) PARTITION BY HASH (player_id) PARTITIONS 10;

CREATE TABLE highscore_data_daily (
  player_id INT UNSIGNED NOT NULL,
  scrape_date DATE NOT NULL,
  scrape_year SMALLINT UNSIGNED AS (YEAR(scrape_date)) STORED NOT NULL,
  scrape_month TINYINT UNSIGNED AS (MONTH(scrape_date)) STORED NOT NULL,
  scrape_week TINYINT UNSIGNED AS (WEEK(scrape_date, 3)) STORED NOT NULL,
  skills JSON DEFAULT NULL,
  activities JSON DEFAULT NULL,
  PRIMARY KEY (player_id, scrape_date)
) PARTITION BY HASH (player_id) PARTITIONS 10;

CREATE TABLE highscore_data_weekly (
  player_id INT UNSIGNED NOT NULL,
  scrape_date DATE NOT NULL,
  scrape_year SMALLINT UNSIGNED AS (YEAR(scrape_date)) STORED NOT NULL,
  scrape_month TINYINT UNSIGNED AS (MONTH(scrape_date)) STORED NOT NULL,
  scrape_week TINYINT UNSIGNED AS (WEEK(scrape_date, 3)) STORED NOT NULL,
  skills JSON DEFAULT NULL,
  activities JSON DEFAULT NULL,
  PRIMARY KEY (player_id, scrape_year, scrape_week)
) PARTITION BY HASH (player_id) PARTITIONS 10;

CREATE TABLE highscore_data_monthly (
  player_id INT UNSIGNED NOT NULL,
  scrape_date DATE NOT NULL,
  scrape_year SMALLINT UNSIGNED AS (YEAR(scrape_date)) STORED NOT NULL,
  scrape_month TINYINT UNSIGNED AS (MONTH(scrape_date)) STORED NOT NULL,
  scrape_week TINYINT UNSIGNED AS (WEEK(scrape_date, 3)) STORED NOT NULL,
  skills JSON DEFAULT NULL,
  activities JSON DEFAULT NULL,
  PRIMARY KEY (player_id, scrape_year, scrape_month)
) PARTITION BY HASH (player_id) PARTITIONS 10;