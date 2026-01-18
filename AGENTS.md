# AGENTS.md - Bot Detector Codebase Guidelines

This document provides guidelines for agentic coding tools working in the Bot Detector repository.

## Build/Lint/Test Commands

### Build Commands
- **Build all projects**: `uv run poly build`
- **Build specific project**: `cd projects/<project_name> && uv build`
- **Sync dependencies**: `uv sync` (run in project directories)
- **Update all locks**: `find . -name "pyproject.toml" -not -path "*/.venv/*" -execdir sh -c 'echo "🔄 Updating lock in $(pwd)"; uv lock' \;`

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
- **Start development environment**: `make docker-dev-restart`
- **Restart full environment**: `make docker-restart`
- **Build Docker containers**: `docker-compose build`

## Code Style Guidelines

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
- **Avoid raw SQL**: Use ORM methods and SQLAlchemy Core for queries
- **Transaction management**: Use proper transaction scoping

```python
# Good
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

### Kafka Patterns
- **Producer configuration**: Use proper serialization and acknowledgment settings
- **Consumer groups**: Use consumer groups for scalable message processing
- **Error handling**: Implement proper error handling and retry logic
- **Topic naming**: Use consistent topic naming conventions

```python
# Good
producer = KafkaProducer(
    bootstrap_servers=kafka_broker,
    value_serializer=lambda x: json.dumps(x).encode(),
    acks="all",
    retries=3
)

try:
    producer.send(
        topic="players.to_scrape",
        value=player_data.model_dump(mode="json")
    )
except KafkaError as e:
    logger.error(f"Failed to send message to Kafka: {e}")
    raise
```

## Project Structure

```
bot-detector/
├── bases/                  # Shared base components
├── components/             # Reusable feature components
├── projects/               # Deployable projects
├── test/                   # Test suite
├── _kafka/                 # Kafka infrastructure
├── _mysql/                 # MySQL infrastructure
└── specs/                  # Specifications
```

## Polylith Architecture Rules

1. **Components**: Self-contained features with business logic
2. **Bases**: Plumbing and API layers that depend on components
3. **Projects**: Deployable artifacts that compose bricks
4. **No circular dependencies**: Components should not depend on bases
5. **Shared interfaces**: Use structs in components for shared contracts

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