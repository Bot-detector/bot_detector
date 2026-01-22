# AGENTS.md - Bot Detector Codebase Guidelines

This document provides guidelines for agentic coding tools working in the Bot Detector repository.

## Build/Lint/Test Commands

### Build Commands
- **Build all projects**: `uv run poly build`
- **Build specific project**: `cd projects/<project_name> && uv build`
- **Sync dependencies**: `uv sync` (run in project directories)
- **Update all locks**: `find . -name "pyproject.toml" -not -path "*/.venv/*" -execdir sh -c 'echo "🔄 Updating lock in $(pwd)"; uv lock' \;`
- **Sync all project directories**: `find . -type f -name "pyproject.toml" -not -path "*/.venv/*" -execdir sh -c 'echo "🔄 syncing in $(pwd)"; uv sync' \;`

### Lint Commands
- **Run Ruff linter**: `ruff check .`
- **Run Ruff with auto-fix**: `ruff check --fix .`
- **Run Ruff on specific file**: `ruff check path/to/file.py`
- **Check specific rule**: `ruff check --select RUF001 .`

### Test Commands
- **Run all tests**: `pytest`
- **Run tests with coverage**: `pytest --cov=bot_detector --cov-report=term-missing`
- **Run specific test file**: `pytest test/path/to/test_file.py`
- **Run single test**: `pytest test/path/to/test_file.py::test_function_name`
- **Run tests with verbose output**: `pytest -v`
- **Run async tests**: `pytest -p pytest_asyncio`
- **Run tests in specific directory**: `pytest test/components/bot_detector/`

### Docker Commands
- **Start development environment**: `docker-compose -f docker-compose-dev.yml up -d --build`
- **Restart full environment**: `docker-compose up -d --build`
- **Build Docker containers**: `docker-compose build`
- **View logs**: `docker-compose logs -f <service_name>`
- **Stop all services**: `docker-compose down`

## Code Style Guidelines

### JSON Serialization

- **Use orjson for fast JSON serialization**: orjson is faster than standard json
- **Import orjson for all JSON operations**: `import orjson`
- **Use with Kafka producers**: orjson is the default serializer for Kafka

```python
# Good
import orjson

# Serialize
data_bytes = orjson.dumps(data_dict)
data_dict = orjson.loads(data_bytes)

# With Kafka producer
value_serializer=lambda v: orjson.dumps(v)

# Bad
import json
data = json.dumps(data)  # Slower, not used in this codebase
```

### Imports
- **Group imports**: Standard library, third-party, local imports (separated by blank lines)
- **Absolute imports**: Prefer absolute imports over relative
- **Type imports**: Import types explicitly when needed
- **Avoid wildcard imports**: Use explicit imports instead of `from module import *`

```python
# Good
from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from bot_detector.database.core import get_session_factory

# Bad
from fastapi import *
```

### Formatting
- **Line length**: 88 characters maximum
- **Indentation**: 4 spaces (no tabs)
- **String quotes**: Single quotes for strings, double quotes for docstrings
- **Trailing commas**: Use trailing commas for multi-line collections
- **Blank lines**: 2 blank lines between top-level functions/classes, 1 blank line between methods

### Types
- **Type hints**: Use Pydantic models and Python type hints extensively
- **Return types**: Always specify return types for functions
- **Optional types**: Use `Optional[T]` or `T | None` for nullable values
- **Generic types**: Use `List[T]`, `Dict[K, V]`, etc. from `typing` module

```python
from typing import Optional, List, Dict
from pydantic import BaseModel

class PlayerData(BaseModel):
    name: str
    level: int
    skills: Dict[str, int]

def get_player_data(player_id: str) -> Optional[PlayerData]:
    # Implementation
    pass
```

### Naming Conventions
- **Variables**: `snake_case` for variables and functions
- **Constants**: `UPPER_SNAKE_CASE` for constants
- **Classes**: `PascalCase` for class names
- **Methods**: `snake_case` for methods
- **Private members**: `_single_underscore_prefix` for protected, `__double_underscore` for private
- **Test functions**: `test_` prefix for test functions

```python
# Good
class PlayerRepository:
    def __init__(self, session_factory):
        self._session_factory = session_factory
        self.__cache = {}
    
    def get_player_by_name(self, name: str):
        pass

# Bad
class player_repository:
    def GetPlayerByName(name):
        pass
```

### Error Handling
- **Specific exceptions**: Catch specific exceptions, not bare `except:`
- **Custom exceptions**: Create custom exception classes for domain-specific errors
- **Logging**: Use structured logging for errors
- **Async error handling**: Use proper async context managers for resource cleanup

```python
# Good
try:
    player = await repository.get_player(player_id)
except PlayerNotFoundError as e:
    logger.error(f"Player not found: {player_id}", exc_info=e)
    raise HTTPException(status_code=404, detail="Player not found")

# Bad
try:
    player = await repository.get_player(player_id)
except:
    print("Error getting player")
```

### Async/Await Patterns
- **Async functions**: Use `async def` for all I/O-bound operations
- **Context managers**: Use `async with` for async context managers
- **Task management**: Use proper task cancellation and timeout handling
- **Avoid blocking calls**: Never use synchronous I/O in async functions

```python
# Good
async def fetch_player_data(player_id: str) -> PlayerData:
    async with aiohttp.ClientSession() as session:
        async with session.get(f"api/players/{player_id}") as response:
            return await response.json()

# Bad
def fetch_player_data(player_id: str) -> PlayerData:
    response = requests.get(f"api/players/{player_id}")
    return response.json()
```

### SQLAlchemy Patterns
- **Async sessions**: Use `AsyncSession` for all database operations
- **Repository pattern**: Encapsulate database operations in repository classes
- **Session factory**: Use `get_session_factory` with proper pool configuration
- **Transaction management**: Use proper transaction scoping with `async with session.begin()`

```python
# Good - Session factory with pool settings
from bot_detector.database.core import get_session_factory

session_factory, engine = get_session_factory(SETTINGS=DBSettings())

# Good - Async session usage
async with session_factory() as session:
    async with session.begin():
        await player_repo.update_many_players(
            async_session=session,
            players_data=players_batch,
        )
        await highscore_repo.insert_highscore_many(
            async_session=session,
            highscore_data=highscore_batch,
        )
        await session.commit()

# Good - Query pattern
async def get_player(session: AsyncSession, player_id: str) -> Optional[Player]:
    result = await session.execute(
        select(Player).where(Player.id == player_id)
    )
    return result.scalar_one_or_none()

# Bad
def get_player(player_id: str):
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        return conn.execute(f"SELECT * FROM players WHERE id = '{player_id}'").fetchone()
```

### FastAPI Patterns
- **Route organization**: Group related routes in routers
- **Dependency injection**: Use FastAPI's dependency injection system
- **Request validation**: Use Pydantic models for request/response validation
- **Error handling**: Use HTTPException for API errors

```python
# Good
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter(prefix="/players", tags=["players"])

@router.get("/{player_id}")
async def get_player(
    player_id: str,
    repository: PlayerRepository = Depends(get_player_repository)
) -> PlayerResponse:
    player = await repository.get_player(player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return PlayerResponse.from_orm(player)
```

### ML/MLflow Patterns

This project uses MLflow for model tracking and serving, with MinIO as the backend.

- **Model loading**: Load models in FastAPI lifespan context
- **Model registry**: Store models in MinIO via MLflow
- **Inference API**: Create REST endpoints for model prediction
- **Settings**: Configure MLflow S3 endpoint URL and AWS credentials

```python
# Good - ML model loading in lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    for name, uri in SETTINGS.MODEL_URIS.items():
        logger.info(f"Loading model: {name} from {uri}")
        model = mlflow.pyfunc.load_model(uri)
        assert model is not None
        models[name] = model
    yield
    models.clear()

# Good - Prediction endpoint
@router.post("/models/{model_name}/predict")
def predict(
    model_name: str,
    data: list[dict],
    models: dict[str, PyFuncModel] = Depends(get_models),
):
    model = models.get(model_name)
    if not model:
        raise HTTPException(status_code=404, detail=f"Model: {model_name} not found")
    prediction = model.predict(data)
    return {"model": model_name, "prediction": prediction}
```

### Logging Patterns

This project uses custom JSON logging with the `logfmt` component for structured logging.

- **JSON logging**: All logs are JSON-formatted for easy parsing
- **Structured data**: Log dicts as JSON fields
- **Log levels**: Use appropriate levels (DEBUG, INFO, WARNING, ERROR)
- **Context**: Include relevant context in log messages

```python
# Good - Structured JSON logging
logger.info(
    f"{player_id=}, {confirmed_ban=}, {possible_ban=}, {limit=}"
)

# Good - Logging with extra structured data
logger.error(
    "Failed to validate HighScoreStruct",
    extra={
        "player_id": _player_id,
        "data": _skills | _activities,
        "errors": e.errors(),
    },
    exc_info=True,
)
```

### Prometheus Metrics Patterns

- **Middleware**: Use PrometheusMiddleware for request tracking
- **Metrics server**: Start Prometheus metrics server on separate port
- **Custom metrics**: Track business metrics as needed

```python
# Good - Start metrics server
from prometheus_client import start_wsgi_server

start_wsgi_server(port=8000)

# Good - Middleware integration
from fastapi import Middleware
from bot_detector.api_ml.core.fastapi.middleware import PrometheusMiddleware

middleware = [
    Middleware(PrometheusMiddleware),
]
```

This project uses MLflow for model tracking and serving, with MinIO as the backend.

- **Model loading**: Load models in FastAPI lifespan context
- **Model registry**: Store models in MinIO via MLflow
- **Inference API**: Create REST endpoints for model prediction
- **Settings**: Configure MLflow S3 endpoint URL and AWS credentials

```python
# Good - ML model loading in lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    for name, uri in SETTINGS.MODEL_URIS.items():
        logger.info(f"Loading model: {name} from {uri}")
        model = mlflow.pyfunc.load_model(uri)
        assert model is not None
        models[name] = model
    yield
    models.clear()

# Good - Prediction endpoint
@router.post("/models/{model_name}/predict")
def predict(
    model_name: str,
    data: list[dict],
    models: dict[str, PyFuncModel] = Depends(get_models),
):
    model = models.get(model_name)
    if not model:
        raise HTTPException(status_code=404, detail=f"Model: {model_name} not found")
    prediction = model.predict(data)
    return {"model": model_name, "prediction": prediction}
```

### Kafka Patterns

This project uses `aiokafka` and `aiokafkaengine` for async Kafka operations.

- **Producer configuration**: Use orjson for serialization, `acks="all"` for reliability
- **Consumer groups**: Use consumer groups for scalable message processing
- **Error handling**: Implement exponential backoff for `KafkaTimeoutError`, retry on failure
- **Topic naming**: Follow these conventions

**Kafka Topics Used:**
- `players.to_scrape` - Tasks for scraper to fetch player data
- `players.scraped` - Successfully scraped player data
- `players.not_found` - Players not found (fallback to RuneMetrics)
- `data.to_predict` - Data ready for ML inference
- `reports.to_insert` - Bot reports from plugins

```python
# Good - Producer with orjson and retry logic
import orjson
import asyncio
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaTimeoutError

producer = AIOKafkaProducer(
    bootstrap_servers=kafka_broker,
    value_serializer=lambda v: orjson.dumps(v),
    acks="all",
)
semaphore = asyncio.Semaphore(value=10)

async def produce_one(data: dict, topic: str):
    retries = 0
    MAX_BACKOFF = 60
    while True:
        async with semaphore:
            try:
                await producer.send(
                    topic=topic,
                    value=data,
                )
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

1. **Components**: Self-contained features with business logic
2. **Bases**: Plumbing and API layers that depend on components
3. **Projects**: Deployable artifacts that compose bricks
4. **No circular dependencies**: Components should not depend on bases
5. **Shared interfaces**: Use structs in components for shared contracts

## Worker/Consumer Patterns

- **Batch processing**: Use `consume_many` with `max_messages` and `timeout_ms`
- **Error recovery**: On failure, re-produce messages and sleep before retry
- **Consumer groups**: Use appropriate group IDs for parallel processing
- **Graceful shutdown**: Properly close consumers, producers, and database connections

```python
# Good - Worker pattern with error recovery
async def consume_many_task(
    max_messages: int,
    max_interval_ms: int,
    consumer: RepoPlayerScrapedConsumer,
    producer: RepoPlayerScrapedProducer,
    session_factory: async_sessionmaker[AsyncSession],
):
    while True:
        try:
            batch, errors = await consumer.consume_many(
                max_messages=max_messages,
                timeout_ms=max_interval_ms,
            )
            logger.info(f"Consumed {len(batch)} records")

            if not batch:
                await asyncio.sleep(15)
                continue

            # Process batch
            await insert_batch(session_factory, batch)

            await consumer.commit()
        except Exception as e:
            logger.error(f"Error consuming: {e}")
            # Re-produce failed messages
            await asyncio.gather(*[producer.produce_one(b) for b in batch])
            await asyncio.sleep(15)
```

## Data Transformation Patterns

- **Use Pydantic for validation**: Validate data shapes with Pydantic models
- **Handle invalid data**: Log errors and skip/transform appropriately
- **Normalize keys**: Normalize dictionary keys (e.g., lowercase for skills/activities)
- **Type safety**: Use proper type hints for transformed data

```python
# Good - Transform and validate
def transform_scraped_struct(
    record: ScrapedStruct,
) -> DataToPredictStruct | None:
    if record.highscore_data is None:
        logger.debug("Highscore data is None")
        return None

    _skills = record.highscore_data.skills or {}
    _skills = {k.lower(): v for k, v in _skills.items() if v is not None}
    _activities = record.highscore_data.activities or {}
    _activities = {k.lower(): v for k, v in _activities.items() if v is not None}

    try:
        _data = HighScoreStruct.model_validate(_skills | _activities)
        return DataToPredictStruct.model_validate({
            "player_id": record.player_data.id,
            "data": _data,
        })
    except ValidationError as e:
        logger.error(
            "Failed to validate HighScoreStruct",
            extra={"player_id": record.player_data.id, "errors": e.errors()},
            exc_info=True,
        )
        return None
```

## Testing Standards

- **Test location**: Tests live in `test/` directory following Polylith structure
- **Test naming**: `test_*.py` files with `test_*` function names
- **Async tests**: Use `pytest-asyncio` for async test functions
- **Fixtures**: Use pytest fixtures for test dependencies
- **Mocking**: Use appropriate mocking for external dependencies

```python
# Example test structure
import pytest
from bot_detector.database.core import get_session_factory

@pytest.mark.asyncio
async def test_get_player():
    # Test implementation
    pass
```

## Development Workflow

1. **Create new component**: `uv run poly create component --name <component_name>`
2. **Create new base**: `uv run poly create base --name <base_name>`
3. **Run tests locally**: `pytest test/components/bot_detector/<component>/`
4. **Sync dependencies**: `uv sync` in relevant project directories
5. **Build for production**: `uv run poly build`

## Environment Variables

- Use `.env` files for local development
- Use `pydantic-settings` for settings management
- Never commit secrets or sensitive data
- Use `PROXY_API_KEY`, `DATABASE_URL` patterns from `.env.example`

## Documentation Standards

- Use docstrings for public modules, classes, and functions
- Follow Google-style docstrings
- Keep README.md updated with architecture diagrams
- Use Mermaid for flowcharts and diagrams

```python
"""Player repository for database operations.

This module provides CRUD operations for player data using SQLAlchemy.
"""

class PlayerRepository:
    """Repository for player data access.
    
    Args:
        session_factory: Async session factory for database connections
        
    Attributes:
        _session_factory: Factory for creating database sessions
    """
    def __init__(self, session_factory):
        self._session_factory = session_factory
```