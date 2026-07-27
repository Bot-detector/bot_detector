SCRAPE_BATCH_SQL = """
    SELECT sdv.scrape_id, sdv.scrape_date, sdv.player_id, pl.name AS player_name
    FROM scraper_data_v3 sdv
    JOIN Players pl ON sdv.player_id = pl.id
    WHERE sdv.scrape_id > :last_id
    ORDER BY sdv.scrape_id ASC
    LIMIT :batch_size
"""


SKILL_RANGE_SQL = """
    SELECT sps.scrape_id, s.skill_name, ps.skill_value
    FROM scraper_player_skill sps
    JOIN player_skill ps ON sps.player_skill_id = ps.player_skill_id
    JOIN skill s ON ps.skill_id = s.skill_id
    WHERE sps.scrape_id BETWEEN :min_id AND :max_id
"""


ACTIVITY_RANGE_SQL = """
    SELECT spa.scrape_id, a.activity_name, pa.activity_value
    FROM scraper_player_activity spa
    JOIN player_activity pa ON spa.player_activity_id = pa.player_activity_id
    JOIN activity a ON pa.activity_id = a.activity_id
    WHERE spa.scrape_id BETWEEN :min_id AND :max_id
"""

FULL_RANGE_SQL = """
SELECT 
    a.scrape_id,
    a.scrape_date,
    a.player_id,
    a.player_name,
    a._name,
    a._value,
    a._type
FROM (
    SELECT 
        sdv.scrape_id,
        sdv.scrape_date,
        sdv.player_id,
        pl.name AS player_name,
        s.skill_name AS _name,
        ps.skill_value AS _value,
        'skill' AS _type
    FROM scraper_data_v3 sdv
    JOIN Players pl ON sdv.player_id = pl.id
    JOIN scraper_player_skill sps ON sdv.scrape_id = sps.scrape_id 
    JOIN player_skill ps ON sps.player_skill_id = ps.player_skill_id
    JOIN skill s ON ps.skill_id = s.skill_id

    UNION ALL

    SELECT 
        sdv.scrape_id,
        sdv.scrape_date,
        sdv.player_id,
        pl.name AS player_name,
        a.activity_name AS _name,
        pa.activity_value AS _value,
        'activity' AS _type
    FROM scraper_data_v3 sdv
    JOIN Players pl ON sdv.player_id = pl.id
    JOIN scraper_player_activity spa ON sdv.scrape_id = spa.scrape_id 
    JOIN player_activity pa ON spa.player_activity_id = pa.player_activity_id
    JOIN activity a ON pa.activity_id = a.activity_id
) a
WHERE a.scrape_id BETWEEN :min_id AND :max_id
ORDER BY a.scrape_id, _type, _name;
"""
