# AGENTS.md – Bot Detector Codebase Guidelines

This repository uses **Polylith**, a software architecture that applies functional thinking at the system scale.  
It enables simple, maintainable, testable, and scalable systems in a monorepo, supporting multiple microservices or apps while sharing code safely.

The intent of this document is to guide **both humans and agents** to make correct architectural and code decisions by default.
## Commands
- Sync all dependencies: 
  - `uv sync`
- Lock a project after dependency updates: 
  - `cd projects/<project> && uv lock`
- Type checking  
  - `uv run mypy`
- Code formatting & linting  
  - `uv run ruff`
- Testing  
  - `uv run pytest`
- Polylith commands (explicit permission required)  
  - `uv run poly create component --name <name>`  
  - `uv run poly create base --name <name>`  
## Repository Guidelines
### Polylith Architecture Rules
1. **Components**  
  - Self-contained, reusable business logic.  
   No framework, transport, or infrastructure concerns.
2. **Bases**  
   Plumbing layers: APIs, workers, schedulers, scrapers, integrations.  
   Bases wire frameworks to components.
3. **Projects**  
   Deployable artifacts.  
   Projects only compose bricks; they contain no business logic.
4. **No Circular Dependencies**  
   - Components MUST NOT depend on bases  
   - Bases MAY depend on components  
   - Projects MAY depend on both
5. **Shared Interfaces**  
   Shared data objects live in components as explicit models  
   (Pydantic models or dataclasses).

### Project Structure
```
bot-detector/  
├── bases/                  # API layer and plumbing (FastAPI apps, workers, scrapers)  
│   └── bot_detector/  
├── components/             # Reusable business logic and integrations  
│   └── bot_detector/  
├── projects/               # Deployable projects (compose bricks for deployment)  
├── test/                   # Workspace-level tests (Polylith standard)
├── _infra/                 # Infrastructure containers and setup
│   ├── _kafka/             # Kafka infrastructure (topic setup scripts)
│   ├── _mysql/             # MySQL infrastructure (database init scripts)
│   ├── _mysql_data/        # MySQL data setup (schema, grants)
│   └── _minio_data/        # MinIO data storage
```
## Code Guidelines
### JSON Serialization
- Use **orjson** for JSON serialization and deserialization
- Prefer serializing Pydantic models for type safety
- Applies primarily to APIs, messaging, and persistence layers
### Imports, Formatting, Types, Naming, Errors, Async
#### Imports
- Sorting command: `uv run ruff check --select I --fix <file>`
#### Types
- Type hints are mandatory
- Prefer Pydantic models or dataclasses for shared data
- Avoid untyped dicts for domain data
#### Naming
- Variables: snake_case  
- Constants: UPPER_SNAKE_CASE  
- Classes: PascalCase  
- Private members: _leading_underscore  
#### Errors
- Handle errors as values `return Exception()`
- Catch **specific exceptions** inside components
- Broad exception handling is allowed **only at base boundaries**
- Never swallow exceptions silently
- Convert exceptions to domain-appropriate errors at API edges
#### Async
- Use async def for all I/O-bound operations
- Use async with for resources
- Never call blocking code inside async paths
## Feature-Based Component Pattern
Components must be organized **by feature**, not by technical role.

Avoid structures like: `components/`
- `interface/`
- `struct/`
- `service/`
Instead, prefer: `components/<component>/<feature>/`
- `struct.py`
- `interface.py`
- `service.py`
- `repository.py`

This keeps related logic co-located and easier to evolve.
## Testing Standards
- All tests live in the workspace-level test/ directory
- File naming: test_*.py
- Use pytest-asyncio for async tests
- Prefer fixtures and explicit mocks
### Testing Pattern – Simplified Functions
- Use standalone `@pytest.mark.asyncio` test functions
- Avoid test classes
- Mock irrelevant dependencies
- Each test should validate a single concern
- Make failure cases explicit and readable
## Environment Variables
- Use **pydantic-settings**
- No direct os.environ access inside business logic
- Validate environment configuration at startup
## Event Queue Pattern Note
The `components/bot_detector/event_queue` area intentionally combines multiple patterns:
- **Structural**
  - **Adapter**: backend-specific adapters (Kafka, memory) implement queue protocols.
- **Creational**
  - **Abstract Factory** (`QueueFactory.create_queue`) chooses backend + queue shape at runtime.

Why this mix:
- Keep base code simple
- Keep transport swappable for testing (`backend_type="memory"`) without changing call sites.
- Keep backend-specific details isolated behind protocols/factory.

## Documentation Standards
Documentation should be **short, relevant, and intentional**.
- Google-style docstrings
- Comments only where intent is non-obvious
- README.md must include:
  - Architecture overview
  - Dependency flow
  - Mermaid diagrams where helpful
## Agent Guardrails (Important)
Agents MUST NOT:
- Introduce new bases without architectural justification
- Add business logic to bases or projects unless requested
- Create shared utility modules without approval
- Bypass components from projects
- Introduce blocking I/O in async paths
- Change Polylith boundaries to “make things easier”

When unsure, **ask before creating new bricks**.
## References
- FastAPI  
  - https://github.com/fastapi/fastapi  
  - https://fastapi.tiangolo.com/
- uv  
  - https://docs.astral.sh/uv/
- Kafka  
  - https://aiokafka.readthedocs.io/en/stable/
- SQLAlchemy  
  - https://docs.sqlalchemy.org/en/20/intro.html
- Polylith  
  - https://polylith.gitbook.io/polylith/  
  - https://davidvujic.github.io/python-polylith-docs/
- Pytest  
  - https://docs.pytest.org/en/stable/
- design-patterns
  - https://refactoring.guru/design-patterns

## Note to the Model – Failure, Uncertainty, and Communication
When an action does not work immediately, or the next step is unclear, the model MUST notify the user.
### When to notify the user
The model must explicitly mention the user when any of the following occur:

- A command, tool, or action fails or produces unexpected results
- Required information, permissions, or context is missing
- Multiple valid approaches exist and no preference is stated
- The model is unsure whether a change aligns with repository rules
- Progress is blocked or assumptions would be required to continue
### How to notify the user
- Clearly state **what was attempted**
- Clearly state **why it failed or is uncertain**
- Clearly state **what is needed to proceed**
- Do not silently retry, guess, or fabricate results
### Required behavior
- Prefer asking one clear, targeted question over making assumptions
- Do not proceed past uncertainty without user acknowledgment
- Do not hide errors behind generic success messages
### Example
> “I attempted to create a new component, but this requires permission per the Polylith rules.  
> Please confirm whether I should proceed or propose an alternative.”

This rule exists to prevent silent failure, architectural drift, and incorrect assumptions.
