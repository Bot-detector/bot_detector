FULL_RANGE_SQL = """
select 
	hd.player_id,
	pl.name as player_name,
	hd.scrape_ts ,
	hd.scrape_date ,
	hd.skills,
	hd.activities 
from highscore_data hd 
join Players pl on hd.player_id = pl.id
where hd.scrape_ts > FROM_UNIXTIME(:start_ts)
order by hd.scrape_ts asc
LIMIT :batch_size
;
"""
