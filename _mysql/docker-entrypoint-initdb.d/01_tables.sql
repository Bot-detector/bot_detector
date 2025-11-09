USE playerdata;
CREATE TABLE Players (
  id INT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(50),
  created_at datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT NULL,
  possible_ban BOOLEAN NOT NULL DEFAULT '0',
  confirmed_ban BOOLEAN NOT NULL DEFAULT '0',
  confirmed_player BOOLEAN NOT NULL DEFAULT '0',
  label_id INTEGER NOT NULL DEFAULT '0',
  label_jagex INTEGER NOT NULL DEFAULT '0',
  ironman BOOLEAN DEFAULT NULL,
  hardcore_ironman BOOLEAN DEFAULT NULL,
  ultimate_ironman BOOLEAN DEFAULT NULL,
  normalized_name VARCHAR(50),
  UNIQUE KEY Unique_name (name)
);

CREATE TABLE migration_hs_v3 (
  player_id INT UNSIGNED NOT NULL
);

-- these tables are for future use
-- CREATE TABLE player (
--   player_id INT UNSIGNED NOT NULL AUTO_INCREMENT,
--   player_name VARCHAR(50) NOT NULL,
--   created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
--   PRIMARY KEY (player_id),
--   UNIQUE KEY Unique_name (player_name)
-- );
-- CREATE TABLE player_attributes (
--   player_id INT UNSIGNED NOT NULL,
--   updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
--   possible_ban BOOLEAN,
--   confirmed_ban BOOLEAN,
--   confirmed_player BOOLEAN,
--   label_id INTEGER,
--   label_jagex INTEGER,
--   PRIMARY KEY (player_id)
--   FOREIGN KEY (player_id) REFERENCES player(player_id)
-- );
-- CREATE TABLE player_attributes_history (
--   player_id INT UNSIGNED NOT NULL,
--   updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
--   possible_ban BOOLEAN,
--   confirmed_ban BOOLEAN,
--   confirmed_player BOOLEAN,
--   time_to_live TIMESTAMP,
--   label_id INTEGER,
--   label_jagex INTEGER,
--   PRIMARY KEY (player_id, updated_at) 
-- ) PARTITION BY HASH (player_id) PARTITIONS 10;
-- Foreign keys are not yet supported in conjunction with partitioning

CREATE TABLE highscore_data_latest (
  player_id INT UNSIGNED NOT NULL,
  scrape_date DATE NOT NULL,
  scrape_year SMALLINT UNSIGNED AS (YEAR(scrape_date)) STORED NOT NULL,
  scrape_month TINYINT UNSIGNED AS (MONTH(scrape_date)) STORED NOT NULL,
  scrape_week TINYINT UNSIGNED AS (WEEK(scrape_date, 3)) STORED NOT NULL,
  skills JSON DEFAULT NULL,
  activities JSON DEFAULT NULL,
  PRIMARY KEY (player_id)
) PARTITION BY HASH (player_id) PARTITIONS 10;

CREATE TABLE highscore_data_daily (
  player_id INT UNSIGNED NOT NULL,
  scrape_date DATE NOT NULL,
  time_to_live DATE NOT NULL,
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
  time_to_live DATE NOT NULL,
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
  time_to_live DATE NOT NULL,
  scrape_year SMALLINT UNSIGNED AS (YEAR(scrape_date)) STORED NOT NULL,
  scrape_month TINYINT UNSIGNED AS (MONTH(scrape_date)) STORED NOT NULL,
  scrape_week TINYINT UNSIGNED AS (WEEK(scrape_date, 3)) STORED NOT NULL,
  skills JSON DEFAULT NULL,
  activities JSON DEFAULT NULL,
  PRIMARY KEY (player_id, scrape_year, scrape_month)
) PARTITION BY HASH (player_id) PARTITIONS 10;

CREATE TABLE prediction_latest (
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  player_id INT NOT NULL,
  model_name VARCHAR(50) NOT NULL,
  prediction VARCHAR(50) NOT NULL,
  confidence DECIMAL(5, 2) NOT NULL,
  predictions JSON DEFAULT NULL,
  PRIMARY KEY (player_id),
  FOREIGN KEY (player_id) REFERENCES Players(id)
);

DELIMITER $$

CREATE TRIGGER trg_prediction_latest_update_timestamp
BEFORE UPDATE ON prediction_latest
FOR EACH ROW
BEGIN
  SET NEW.created_at = CURRENT_TIMESTAMP;
END$$

DELIMITER ;

CREATE TABLE prediction (
  prediction_id INT UNSIGNED NOT NULL AUTO_INCREMENT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  player_id INT NOT NULL,
  model_name VARCHAR(50) NOT NULL,
  prediction VARCHAR(50) NOT NULL,
  confidence DECIMAL(5, 2) NOT NULL,
  predictions JSON DEFAULT NULL,
  PRIMARY KEY (prediction_id),
  FOREIGN KEY (player_id) REFERENCES Players(id),
  UNIQUE KEY idx_unique_prediction (player_id, model_name)
);

CREATE TABLE Predictions (
  id INT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(12),
  prediction VARCHAR(50),
  created TIMESTAMP,
  predicted_confidence DECIMAL(5, 2),
  real_player DECIMAL(5, 2) DEFAULT 0,
  pvm_melee_bot DECIMAL(5, 2) DEFAULT 0,
  smithing_bot DECIMAL(5, 2) DEFAULT 0,
  magic_bot DECIMAL(5, 2) DEFAULT 0,
  fishing_bot DECIMAL(5, 2) DEFAULT 0,
  mining_bot DECIMAL(5, 2) DEFAULT 0,
  crafting_bot DECIMAL(5, 2) DEFAULT 0,
  pvm_ranged_magic_bot DECIMAL(5, 2) DEFAULT 0,
  pvm_ranged_bot DECIMAL(5, 2) DEFAULT 0,
  hunter_bot DECIMAL(5, 2) DEFAULT 0,
  fletching_bot DECIMAL(5, 2) DEFAULT 0,
  clue_scroll_bot DECIMAL(5, 2) DEFAULT 0,
  lms_bot DECIMAL(5, 2) DEFAULT 0,
  agility_bot DECIMAL(5, 2) DEFAULT 0,
  wintertodt_bot DECIMAL(5, 2) DEFAULT 0,
  runecrafting_bot DECIMAL(5, 2) DEFAULT 0,
  zalcano_bot DECIMAL(5, 2) DEFAULT 0,
  woodcutting_bot DECIMAL(5, 2) DEFAULT 0,
  thieving_bot DECIMAL(5, 2) DEFAULT 0,
  soul_wars_bot DECIMAL(5, 2) DEFAULT 0,
  cooking_bot DECIMAL(5, 2) DEFAULT 0,
  vorkath_bot DECIMAL(5, 2) DEFAULT 0,
  barrows_bot DECIMAL(5, 2) DEFAULT 0,
  herblore_bot DECIMAL(5, 2) DEFAULT 0,
  zulrah_bot DECIMAL(5, 2) DEFAULT 0,
  gauntlet_bot DECIMAL(5, 2) DEFAULT 0,
  nex_bot DECIMAL(5, 2) DEFAULT 0,
  unknown_bot DECIMAL(5, 2) DEFAULT 0
);

CREATE TABLE PredictionsFeedback (
  id INT PRIMARY KEY AUTO_INCREMENT,
  ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  voter_id INT NOT NULL,
  subject_id INT NOT NULL,
  prediction VARCHAR(50) NOT NULL,
  confidence FLOAT NOT NULL,
  vote INT NOT NULL DEFAULT '0',
  feedback_text TEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci,
  reviewed TINYINT NOT NULL DEFAULT '0',
  reviewer_id INT DEFAULT NULL,
  user_notified TINYINT NOT NULL DEFAULT '0',
  proposed_label VARCHAR(50) DEFAULT NULL,
  UNIQUE KEY Unique_Vote (
    prediction,
    subject_id,
    voter_id
  ) USING BTREE,
  CONSTRAINT FK_Subject_ID FOREIGN KEY (subject_id) REFERENCES Players (id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT FK_Voter_ID FOREIGN KEY (voter_id) REFERENCES Players (id) ON DELETE RESTRICT ON UPDATE RESTRICT
);
CREATE TABLE report_sighting (
  report_sighting_id INT UNSIGNED NOT NULL AUTO_INCREMENT,
  reporting_id INT UNSIGNED NOT NULL,
  reported_id INT UNSIGNED NOT NULL,
  manual_detect TINYINT(1) DEFAULT 0,
  PRIMARY key (report_sighting_id),
  UNIQUE KEY unique_sighting (reporting_id, reported_id, manual_detect),
  KEY idx_reported_id (reported_id)
);
CREATE TABLE report_gear (
  report_gear_id INT UNSIGNED NOT NULL AUTO_INCREMENT,
  equip_head_id SMALLINT UNSIGNED DEFAULT NULL,
  equip_amulet_id SMALLINT UNSIGNED DEFAULT NULL,
  equip_torso_id SMALLINT UNSIGNED DEFAULT NULL,
  equip_legs_id SMALLINT UNSIGNED DEFAULT NULL,
  equip_boots_id SMALLINT UNSIGNED DEFAULT NULL,
  equip_cape_id SMALLINT UNSIGNED DEFAULT NULL,
  equip_hands_id SMALLINT UNSIGNED DEFAULT NULL,
  equip_weapon_id SMALLINT UNSIGNED DEFAULT NULL,
  equip_shield_id SMALLINT UNSIGNED DEFAULT NULL,
  PRIMARY key (report_gear_id),
  UNIQUE KEY unique_gear (
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
);
CREATE TABLE report_location (
  report_location_id INT UNSIGNED NOT NULL AUTO_INCREMENT,
  region_id MEDIUMINT UNSIGNED NOT NULL,
  x_coord MEDIUMINT UNSIGNED NOT NULL,
  y_coord MEDIUMINT UNSIGNED NOT NULL,
  z_coord MEDIUMINT UNSIGNED NOT NULL,
  PRIMARY key (report_location_id),
  UNIQUE KEY unique_location (region_id, x_coord, y_coord, z_coord)
);
CREATE TABLE report (
  report_sighting_id INT UNSIGNED NOT NULL,
  report_location_id INT UNSIGNED NOT NULL,
  report_gear_id INT UNSIGNED NOT NULL,
  created_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  reported_at timestamp NOT NULL,
  on_members_world TINYINT(1) DEFAULT NULL,
  on_pvp_world TINYINT(1) DEFAULT NULL,
  world_number SMALLINT UNSIGNED DEFAULT NULL,
  region_id MEDIUMINT UNSIGNED NOT NULL,
  PRIMARY key (
    report_sighting_id,
    report_location_id,
    region_id
  )
);

CREATE TABLE `Labels` (
  `id` int NOT NULL AUTO_INCREMENT,
  `label` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `Unique_label` (`label`) USING BTREE
);

INSERT INTO Labels (label) VALUES
	 ('Unknown'),
	 ('Real_Player'),
	 ('Wintertodt_bot'),
	 ('Mining_bot'),
	 ('Hunter_bot'),
	 ('Herblore_bot'),
	 ('Fletching_bot'),
	 ('Fishing_bot'),
	 ('Crafting_bot'),
	 ('Cooking_bot'),
	 ('Woodcutting_bot'),
	 ('Smithing_bot'),
	 ('Magic_bot'),
	 ('PVM_Ranged_Magic_bot'),
	 ('Agility_bot'),
	 ('Zalcano_bot'),
	 ('Runecrafting_bot'),
	 ('PVM_Ranged_bot'),
	 ('PVM_Melee_bot'),
	 ('Thieving_bot'),
	 ('LMS_bot'),
	 ('Fishing_Cooking_bot'),
	 ('mort_myre_fungus_bot'),
	 ('temp_real_player'),
	 ('Soul_Wars_bot'),
	 ('Construction_Magic_bot'),
	 ('Vorkath_bot'),
	 ('Clue_Scroll_bot'),
	 ('Barrows_bot'),
	 ('Woodcutting_Mining_bot'),
	 ('Woodcutting_Firemaking_bot'),
	 ('Mage_Guild_Store_bot'),
	 ('Phosani_bot'),
	 ('Unknown_bot'),
	 ('Blast_mine_bot'),
	 ('Zulrah_bot'),
	 ('test_label'),
	 ('Nex_bot'),
	 ('Gauntlet_bot');

CREATE TABLE `scraper_data_v3` (
  `scrape_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `scrape_ts` datetime NOT NULL,
  `scrape_date` date NOT NULL,
  `player_id` int NOT NULL,
  PRIMARY KEY (`scrape_id`),
  UNIQUE KEY `unique_player_scrape` (`player_id`,`scrape_date`),
  KEY `idx_scrape_ts` (`scrape_ts`)
);

CREATE TABLE `scraper_player_skill` (
  `scrape_id` bigint unsigned NOT NULL,
  `player_skill_id` bigint unsigned NOT NULL,
  PRIMARY KEY (`scrape_id`,`player_skill_id`),
  KEY `idx_player_skill_id` (`player_skill_id`)
);

CREATE TABLE `scraper_player_activity` (
  `scrape_id` bigint unsigned NOT NULL,
  `player_activity_id` bigint unsigned NOT NULL,
  PRIMARY KEY (`scrape_id`,`player_activity_id`),
  KEY `idx_player_activity_id` (`player_activity_id`)
);

CREATE TABLE `player_skill` (
  `player_skill_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `skill_id` tinyint unsigned NOT NULL,
  `skill_value` int unsigned NOT NULL DEFAULT '0',
  PRIMARY KEY (`player_skill_id`),
  UNIQUE KEY `unique_skill_value` (`skill_id`,`skill_value`)
);

CREATE TABLE `player_activity` (
  `player_activity_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `activity_id` tinyint unsigned NOT NULL,
  `activity_value` int unsigned NOT NULL DEFAULT '0',
  PRIMARY KEY (`player_activity_id`),
  UNIQUE KEY `unique_activity_value` (`activity_id`,`activity_value`)
);

CREATE TABLE `skill` (
  `skill_id` tinyint unsigned NOT NULL AUTO_INCREMENT,
  `skill_name` varchar(50) NOT NULL,
  PRIMARY KEY (`skill_id`),
  UNIQUE KEY `unique_skill_name` (`skill_name`)
);

CREATE TABLE `activity` (
  `activity_id` tinyint unsigned NOT NULL AUTO_INCREMENT,
  `activity_name` varchar(50) NOT NULL,
  PRIMARY KEY (`activity_id`),
  UNIQUE KEY `unique_activity_name` (`activity_name`)
);