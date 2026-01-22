# AGENTS.md - Bot Detector Codebase Guidelines

## Commands
| Build | `uv run poly build` \| `cd projects/<name> && uv build` \| `uv sync` |
| Lint | `ruff check .` \| `ruff check --fix .` |
| Test | `pytest` \| `pytest --cov=bot_detector` \| `pytest -p pytest_asyncio` |
| Docker | `docker-compose -f docker-compose-dev.yml up -d --build` \| `docker-compose logs -f <service>` \| `docker-compose down` |

## Code Style Guidelines

### JSON Serialization
- Use `orjson` for all JSON operations (`import orjson`, `orjson.dumps()`, `orjson.loads()`)
- Kafka: `value_serializer=lambda v: orjson.dumps(v)`

### Imports/Formatting/Types/Naming/Error/Async
- **Imports**: stdlib → third-party → local, absolute, no wildcards
- **Format**: 88 chars, 4 spaces, single quotes, trailing commas
- **Types**: Always use hints, Pydantic models or datclasses
- **Naming**: variables:`snake_case`, constants:`UPPER_SNAKE_CASE`, classes:`PascalCase`, `_private`, `test_*`
- **Errors**: Catch specific, wide errors are preferred with global exception catching
- **Async**: `async def` for I/O, `async with`, no blocking calls

### Code Examples
```python
from fastapi import FastAPI
from bot_detector.database.core import get_session_factory
from typing import Optional

def get_player_data(player_id: str) -> Optional[PlayerData]:
    pass

class PlayerRepository:
    def __init__(self, session_factory):
        self._session_factory = session_factory

try:
    player = await repository.get_player(player_id)
except PlayerNotFoundError as e:
    logger.error(f"Player not found: {player_id}", exc_info=e)
    raise HTTPException(status_code=404, detail="Player not found")

async def fetch_player_data(player_id: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"api/players/{player_id}") as response:
            return await response.json()

session_factory, engine = get_session_factory(SETTINGS=DBSettings())
async with session_factory() as session:
    async with session.begin():
        await player_repo.update_many_players(async_session=session, players_data=batch)

from fastapi import APIRouter, Depends, HTTPException
router = APIRouter(prefix="/players", tags=["players"])
@router.get("/{player_id}")
async def get_player(player_id: str, repository: PlayerRepository = Depends(get_player_repository)):
    player = await repository.get_player(player_id)
    if not player: raise HTTPException(status_code=404, detail="Player not found")

@asynccontextmanager
async def lifespan(app: FastAPI):
    for name, uri in SETTINGS.MODEL_URIS.items():
        models[name] = mlflow.pyfunc.load_model(uri)
    yield
    models.clear()

logger.info(f"{player_id=}, {confirmed_ban=}")
logger.error("Failed to validate HighScoreStruct", extra={"player_id": _player_id, "errors": e.errors()}, exc_info=True)

from prometheus_client import start_wsgi_server
start_wsgi_server(port=8000)
middleware = [Middleware(PrometheusMiddleware)]
```

### Kafka
- Use `aiokafka`, orjson, `acks="all"`, consumer groups, exponential backoff

**Topics**: `players.to_scrape`, `players.scraped`, `players.not_found`, `data.to_predict`, `reports.to_insert`

```python
producer = AIOKafkaProducer(bootstrap_servers=kafka_broker, value_serializer=lambda v: orjson.dumps(v), acks="all")
async def produce_one(data: dict, topic: str):
    retries, MAX_BACKOFF = 0, 60
    while True:
        async with semaphore:
            try:
                await producer.send(topic=topic, value=data)
                break
            except KafkaTimeoutError:
                retries += 1
                logger.warning(f"KafkaTimeoutError - {topic=} {retries=}")
                await asyncio.sleep(min(2**retries, MAX_BACKOFF))
```

## Project Structure
```
bot-detector/
├── bases/                  # API layer and plumbing (FastAPI apps, workers, scrapers)
│   └── bot_detector/
│       ├── api_public/       # Public API endpoints
│       ├── api_ml/          # ML inference API
│       ├── worker_hiscore/   # Highscore data processing worker
│       ├── worker_ml/        # ML prediction worker
│       ├── worker_report/    # Report processing worker
│       ├── hiscore_scraper/  # Highscore scraper
│       ├── runemetrics_scraper/ # RuneMetrics fallback scraper
│       └── website/         # Web frontend
├── components/             # Reusable business logic and integrations
│   └── bot_detector/
│       ├── database/        # ORM models, repositories, session factory
│       ├── kafka/          # Kafka producers/consumers, base classes
│       ├── structs/        # Pydantic data models (shared DTOs)
│       ├── logfmt/         # JSON logging formatter
│       ├── ml_api/         # ML API client for inference
│       ├── proxy_manager/   # Proxy rotation for scraping
│       └── runemetrics_api/ # RuneMetrics API client
├── projects/               # Deployable projects (compose bricks for deployment)
│   ├── api_public/
│   ├── api_ml/
│   ├── worker_hiscore/
│   ├── worker_ml/
│   ├── worker_report/
│   ├── hiscore_scraper/
│   ├── runemetrics_scraper/
│   └── website/
├── test/                   # Test suite (workspace-level per Polylith)
├── _kafka/                 # Kafka infrastructure (topic setup scripts)
├── _mysql/                 # MySQL infrastructure (database init scripts)
└── specs/                  # Specifications
```

## Polylith Architecture Rules
1. **Components**: Self-contained reusable features with business logic
2. **Bases**: Plumbing and API layers that depend on components
3. **Projects**: Deployable artifacts that compose bricks
4. **No circular dependencies**: Components should not depend on bases
5. **Shared interfaces**: Use structs in components for shared contracts

## Worker/Consumer Patterns
- Batch processing: `consume_many` with `max_messages`/`timeout_ms`
- Error recovery: re-produce messages on failure, sleep before retry
- Consumer groups for parallel processing, graceful shutdown

```python
async def consume_many_task(max_messages, max_interval_ms, consumer, producer, session_factory):
    while True:
        try:
            batch, errors = await consumer.consume_many(max_messages=max_messages, timeout_ms=max_interval_ms)
            if not batch:
                await asyncio.sleep(15)
                continue
            await insert_batch(session_factory, batch)
            await consumer.commit()
        except Exception as e:
            logger.error(f"Error consuming: {e}")
            await asyncio.gather(*[producer.produce_one(b) for b in batch])
            await asyncio.sleep(15)
```

## Data Transformation Patterns
- Pydantic for validation, log errors, normalize keys (lowercase), type hints

```python
def transform_scraped_struct(record: ScrapedStruct) -> DataToPredictStruct | None:
    if record.highscore_data is None: return None
    _skills = {k.lower(): v for k, v in (record.highscore_data.skills or {}).items() if v is not None}
    _activities = {k.lower(): v for k, v in (record.highscore_data.activities or {}).items() if v is not None}
    try:
        _data = HighScoreStruct.model_validate(_skills | _activities)
        return DataToPredictStruct.model_validate({"player_id": record.player_data.id, "data": _data})
    except ValidationError as e:
        logger.error("Failed to validate HighScoreStruct", extra={"player_id": record.player_data.id, "errors": e.errors()}, exc_info=True)
        return None
```

## Testing Standards
- `test/` directory, `test_*.py` files, `pytest-asyncio` for async, fixtures, mocking

```python
import pytest
from bot_detector.database.core import get_session_factory

@pytest.mark.asyncio
async def test_get_player():
    pass
```

## Development Workflow
1. `uv run poly create component --name <name>`
2. `uv run poly create base --name <name>`
3. `pytest test/components/bot_detector/<component>/`
4. `uv sync` in project directories
5. `uv run poly build`

## Environment Variables
- `.env` files, `pydantic-settings`, no commits, patterns: `PROXY_API_KEY`, `DATABASE_URL`

## Documentation Standards
- Docstrings (Google-style), README.md with architecture diagrams, Mermaid

```python
"""Player repository for database operations."""
class PlayerRepository:
    """Repository for player data access."""
    def __init__(self, session_factory):
        self._session_factory = session_factory
```