USE playerdata;

CREATE TABLE Labels (
  id int NOT NULL AUTO_INCREMENT,
  label varchar(50) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY Unique_label (label) USING BTREE
)
;

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
    normalized_name TEXT
);

CREATE TABLE Reports (
    ID BIGINT PRIMARY KEY AUTO_INCREMENT,
    created_at TIMESTAMP,
    reportedID INT,
    reportingID INT,
    region_id INT,
    x_coord INT,
    y_coord INT,
    z_coord INT,
    timestamp TIMESTAMP,
    manual_detect SMALLINT,
    on_members_world INT,
    on_pvp_world SMALLINT,
    world_number INT,
    equip_head_id INT,
    equip_amulet_id INT,
    equip_torso_id INT,
    equip_legs_id INT,
    equip_boots_id INT,
    equip_cape_id INT,
    equip_hands_id INT,
    equip_weapon_id INT,
    equip_shield_id INT,
    equip_ge_value BIGINT,
    CONSTRAINT FK_Reported_Players_id FOREIGN KEY (reportedID) REFERENCES Players (id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT FK_Reporting_Players_id FOREIGN KEY (reportingID) REFERENCES Players (id) ON DELETE RESTRICT ON UPDATE RESTRICT
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
    unknown_bot DECIMAL(5, 2) DEFAULT 0
);

CREATE TABLE playerHiscoreData (
  id bigint NOT NULL AUTO_INCREMENT,
  timestamp datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  ts_date date DEFAULT NULL,
  Player_id int NOT NULL,
  total bigint DEFAULT '0',
  attack int DEFAULT '0',
  defence int DEFAULT '0',
  strength int DEFAULT '0',
  hitpoints int DEFAULT '0',
  ranged int DEFAULT '0',
  prayer int DEFAULT '0',
  magic int DEFAULT '0',
  cooking int DEFAULT '0',
  woodcutting int DEFAULT '0',
  fletching int DEFAULT '0',
  fishing int DEFAULT '0',
  firemaking int DEFAULT '0',
  crafting int DEFAULT '0',
  smithing int DEFAULT '0',
  mining int DEFAULT '0',
  herblore int DEFAULT '0',
  agility int DEFAULT '0',
  thieving int DEFAULT '0',
  slayer int DEFAULT '0',
  farming int DEFAULT '0',
  runecraft int DEFAULT '0',
  hunter int DEFAULT '0',
  construction int DEFAULT '0',
  league int DEFAULT '0',
  bounty_hunter_hunter int DEFAULT '0',
  bounty_hunter_rogue int DEFAULT '0',
  cs_all int DEFAULT '0',
  cs_beginner int DEFAULT '0',
  cs_easy int DEFAULT '0',
  cs_medium int DEFAULT '0',
  cs_hard int DEFAULT '0',
  cs_elite int DEFAULT '0',
  cs_master int DEFAULT '0',
  lms_rank int DEFAULT '0',
  soul_wars_zeal int DEFAULT '0',
  abyssal_sire int DEFAULT '0',
  alchemical_hydra int DEFAULT '0',
  barrows_chests int DEFAULT '0',
  bryophyta int DEFAULT '0',
  callisto int DEFAULT '0',
  cerberus int DEFAULT '0',
  chambers_of_xeric int DEFAULT '0',
  chambers_of_xeric_challenge_mode int DEFAULT '0',
  chaos_elemental int DEFAULT '0',
  chaos_fanatic int DEFAULT '0',
  commander_zilyana int DEFAULT '0',
  corporeal_beast int DEFAULT '0',
  crazy_archaeologist int DEFAULT '0',
  dagannoth_prime int DEFAULT '0',
  dagannoth_rex int DEFAULT '0',
  dagannoth_supreme int DEFAULT '0',
  deranged_archaeologist int DEFAULT '0',
  general_graardor int DEFAULT '0',
  giant_mole int DEFAULT '0',
  grotesque_guardians int DEFAULT '0',
  hespori int DEFAULT '0',
  kalphite_queen int DEFAULT '0',
  king_black_dragon int DEFAULT '0',
  kraken int DEFAULT '0',
  kreearra int DEFAULT '0',
  kril_tsutsaroth int DEFAULT '0',
  mimic int DEFAULT '0',
  nex int DEFAULT '0',
  nightmare int DEFAULT '0',
  phosanis_nightmare int DEFAULT '0',
  obor int DEFAULT '0',
  phantom_muspah int DEFAULT '0',
  sarachnis int DEFAULT '0',
  scorpia int DEFAULT '0',
  skotizo int DEFAULT '0',
  tempoross int DEFAULT '0',
  the_gauntlet int DEFAULT '0',
  the_corrupted_gauntlet int DEFAULT '0',
  theatre_of_blood int DEFAULT '0',
  theatre_of_blood_hard int DEFAULT '0',
  thermonuclear_smoke_devil int DEFAULT '0',
  tombs_of_amascut int DEFAULT '0',
  tombs_of_amascut_expert int DEFAULT '0',
  tzkal_zuk int DEFAULT '0',
  tztok_jad int DEFAULT '0',
  venenatis int DEFAULT '0',
  vetion int DEFAULT '0',
  vorkath int DEFAULT '0',
  wintertodt int DEFAULT '0',
  zalcano int DEFAULT '0',
  zulrah int DEFAULT '0',
  rifts_closed int DEFAULT '0',
  artio int DEFAULT '0',
  calvarion int DEFAULT '0',
  duke_sucellus int DEFAULT '0',
  spindel int DEFAULT '0',
  the_leviathan int DEFAULT '0',
  the_whisperer int DEFAULT '0',
  vardorvis int DEFAULT '0',
  PRIMARY KEY (id),
  UNIQUE KEY idx_playerHiscoreData_Player_id_timestamp (Player_id,timestamp),
  UNIQUE KEY Unique_player_date (Player_id,ts_date),
  CONSTRAINT FK_Players_id FOREIGN KEY (Player_id) REFERENCES Players (id) ON DELETE RESTRICT ON UPDATE RESTRICT
);

/*
-- V3
*/
CREATE TABLE skill (
    skill_id tinyint unsigned NOT NULL AUTO_INCREMENT,
    skill_name varchar(50) NOT NULL,
    PRIMARY KEY (skill_id),
    UNIQUE KEY unique_skill_name (skill_name)
);

CREATE TABLE activity (
    activity_id tinyint unsigned NOT NULL AUTO_INCREMENT,
    activity_name varchar(50) NOT NULL,
    PRIMARY KEY (activity_id),
    UNIQUE KEY unique_activity_name (activity_name)
);

CREATE TABLE player_skill (
    player_skill_id BIGINT unsigned NOT NULL AUTO_INCREMENT,
    skill_id tinyint unsigned NOT NULL,
    skill_value int unsigned NOT NULL DEFAULT '0',
    PRIMARY KEY (player_skill_id),
    UNIQUE KEY unique_skill_value (skill_id, skill_value)
);

CREATE TABLE player_activity (
    player_activity_id bigint unsigned NOT NULL AUTO_INCREMENT,
    activity_id tinyint unsigned NOT NULL,
    activity_value int unsigned NOT NULL DEFAULT '0',
    PRIMARY KEY (player_activity_id),
    UNIQUE KEY unique_activity_value (activity_id, activity_value)
);

CREATE TABLE scraper_data_v3 (
    scrape_id bigint unsigned NOT NULL AUTO_INCREMENT,
    scrape_ts DATETIME NOT NULL,
    scrape_date DATE NOT NULL,
    player_id INT NOT NULL,
    PRIMARY KEY (scrape_id),
    UNIQUE KEY unique_player_scrape (player_id, scrape_date),
    INDEX idx_scrape_ts (scrape_ts)
);

CREATE TABLE scraper_player_skill (
    scrape_id BIGINT unsigned NOT NULL,
    player_skill_id BIGINT unsigned NOT NULL,
    PRIMARY KEY (scrape_id, player_skill_id),
    KEY idx_scrape_id (scrape_id),
    KEY idx_player_skill_id (player_skill_id)
)
PARTITION BY HASH (scrape_id) PARTITIONS 10;

CREATE TABLE scraper_player_activity (
    scrape_id BIGINT unsigned NOT NULL,
    player_activity_id BIGINT unsigned NOT NULL,
    PRIMARY KEY (scrape_id, player_activity_id),
    KEY idx_scrape_id (scrape_id),
    KEY idx_player_activity_id (player_activity_id)
)
PARTITION BY HASH (scrape_id) PARTITIONS 10;
