USE playerdata;

INSERT INTO Labels (id, label)
VALUES
    (1, 'Real_Player'),
    (4, 'Wintertodt_bot'),
    (5, 'Mining_bot'),
    (7, 'Hunter_bot'),
    (8, 'Herblore_bot'),
    (9, 'Fletching_bot'),
    (10, 'Fishing_bot'),
    (11, 'Crafting_bot'),
    (12, 'Cooking_bot'),
    (13, 'Woodcutting_bot'),
    (15, 'Smithing_bot'),
    (17, 'Magic_bot'),
    (19, 'PVM_Ranged_Magic_bot'),
    (21, 'Agility_bot'),
    (27, 'Zalcano_bot'),
    (38, 'Runecrafting_bot'),
    (40, 'PVM_Ranged_bot'),
    (41, 'PVM_Melee_bot'),
    (42, 'Thieving_bot'),
    (52, 'LMS_bot'),
    (56, 'Fishing_Cooking_bot'),
    (57, 'mort_myre_fungus_bot'),
    (59, 'temp_real_player'),
    (61, 'Soul_Wars_bot'),
    (64, 'Construction_Magic_bot'),
    (65, 'Vorkath_bot'),
    (66, 'Clue_Scroll_bot'),
    (67, 'Barrows_bot'),
    (76, 'Woodcutting_Mining_bot'),
    (
        77, 'Woodcutting_Firemaking_bot'
    ),
    (84, 'Mage_Guild_Store_bot'),
    (87, 'Phosani_bot'),
    (89, 'Unknown_bot'),
    (90, 'Blast_mine_bot'),
    (91, 'Zulrah_bot'),
    (92, 'test_label'),
    (109, 'Nex_bot'),
    (110, 'Gauntlet_bot');

INSERT INTO Labels (label) VALUES ("Unkown");
UPDATE Labels set id=0 where label="Unkown";


INSERT INTO skill (skill_name) VALUES
('attack'), ('defence'), ('strength'), ('hitpoints'), ('ranged'), ('prayer'),
('magic'), ('cooking'), ('woodcutting'), ('fletching'), ('fishing'), ('firemaking'),
('crafting'), ('smithing'), ('mining'), ('herblore'), ('agility'), ('thieving'),
('slayer'), ('farming'), ('runecraft'), ('hunter'), ('construction')
;

INSERT INTO activity (activity_name) VALUES
('league'), ('bounty_hunter_hunter'), ('bounty_hunter_rogue'), ('cs_all'), ('cs_beginner'),
('cs_easy'), ('cs_medium'), ('cs_hard'), ('cs_elite'), ('cs_master'), ('lms_rank'),
('soul_wars_zeal'), ('abyssal_sire'), ('alchemical_hydra'), ('barrows_chests'), ('bryophyta'),
('callisto'), ('cerberus'), ('chambers_of_xeric'), ('chambers_of_xeric_challenge_mode'),
('chaos_elemental'), ('chaos_fanatic'), ('commander_zilyana'), ('corporeal_beast'),
('crazy_archaeologist'), ('dagannoth_prime'), ('dagannoth_rex'), ('dagannoth_supreme'),
('deranged_archaeologist'), ('general_graardor'), ('giant_mole'), ('grotesque_guardians'),
('hespori'), ('kalphite_queen'), ('king_black_dragon'), ('kraken'), ('kreearra'),
('kril_tsutsaroth'), ('mimic'), ('nightmare'), ('nex'), ('phosanis_nightmare'), ('obor'),
('phantom_muspah'), ('sarachnis'), ('scorpia'), ('skotizo'), ('tempoross'), ('the_gauntlet'),
('the_corrupted_gauntlet'), ('theatre_of_blood'), ('theatre_of_blood_hard'),
('thermonuclear_smoke_devil'), ('tombs_of_amascut'), ('tombs_of_amascut_expert'), ('tzkal_zuk'),
('tztok_jad'), ('venenatis'), ('vetion'), ('vorkath'), ('wintertodt'), ('zalcano'), ('zulrah'),
('rifts_closed'), ('artio'), ('calvarion'), ('duke_sucellus'), ('spindel'), ('the_leviathan'),
('the_whisperer'), ('vardorvis')
;
