documentation on the architecture https://davidvujic.github.io/python-polylith-docs/

basic commands
```sh
# create a base
uv run poly create base --name my_base

# create a component
uv run poly create component --name my_component

# create a project
uv run poly create project --name scraper
```


# scraping
idea for topic naming

Topic for player data to scrape:
players.to_scrape

Topic for scraped player data (hiscores and player data):
players.scraped

Topic for player data not found in hiscores (advanced scraping):
players.not_found

idea for data structure
```json
{
  "metadata": {
    "id": "uuid",
    "timestamp": "2024-12-25T12:34:56Z",
    "source": "game_api"
  },
  "player_data": {
    "player_name": "example_user",
    ...
  },
  "hiscore_data":{
    "player_name": "example_user",
    ...
  }
}
``` 