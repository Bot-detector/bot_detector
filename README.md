# Setup

## Requirements
- [Docker](https://docs.docker.com/desktop/setup/install/linux/)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- api key: [Webshare](https://www.webshare.io/?referral_code=qvpjdwxqsblt)

## General Setup

1. create an .env file from the .env.example contents
2. Build and start the Docker container:
    this will restart the docker compose file and create the entire project including mysql-database & kafka-queue
    ```sh
    make docker-restart
    ```
    or if you want to exec into a debug container and run the code
    ```sh
    make docker-dev-restart
    ```
## Other Setup
### Web Scraper

1. Generate an API key from [Webshare](https://www.webshare.io/?referral_code=qvpjdwxqsblt).
2. Copy the contents of `.env.example` to a new `.env` file.
3. Replace `<api key>` in the `.env` file with your API key:

    ```env
    PROXY_API_KEY="<api key>"
    ```

# Project Standards
## Definitions
- **Business logic**: the rules that determine how the domain behaves; validations, decisions, orchestration of use-cases, state transitions, etc.
- **Plumbing**: transport/infrastructure glue (HTTP routing, request parsing, wiring dependencies) that carries inputs to the correct business logic and returns the result.
- **Feature**: a cohesive capability (feedback reporting, player scraping, proxy rotation, etc.) that owns its domain rules, ~~DTOs~~ structs, ports, and integrations. Each feature lives inside a component so it can be reused by multiple bases/projects without duplication.
- **Models** = SQLAlchemy ORM classes mapped to concrete tables (live under `components/bot_detector/database/**/models`). Only the persistence layer (repositories/adapters that talk to storage) should touch them.
- **Structs** = Pydantic data shapes (requests/responses/contracts) shared across components/bases; they live under `components/bot_detector/structs` and replace the old “DTO” term.
- **Service**: the domain façade exposed by a component (e.g., `PlayerService`). A service orchestrates one cohesive use-case—validation, repositories, messaging, caching—and is what bases call once they finish plumbing work.
- **Repository**: a persistence/adapter layer focused solely on talking to infrastructure (SQLAlchemy, Kafka, S3, HTTP APIs, etc.). Repositories are consumed by services and do not contain orchestration or HTTP-specific logic.
- **Manager**: an infrastructure helper that owns shared resources (Kafka producers, sessions, caches). Managers live alongside plumbing or support libraries and keep long-lived connections healthy.
- **Cache**: lightweight, in-process memoization layers (like `SimpleALRUCache`) that services can use for hot-path data. Caches never contain business logic; they simply store/retrieve entities to reduce load on repositories.

## Working Standards
- **Components** encapsulate each feature’s business logic plus adapters, and may depend on other components/libraries only. Services may call repositories/adapters but never import FastAPI or base code.
- **Bases** expose public APIs and must stay thin: they handle routing, validation, dependency wiring, and immediately delegate to services. Bases never import ORM models or implement business rules.
- **Projects** only compose bricks + libraries into deployable artifacts; they hold wiring/config, never feature code.
- **Shared structs** (DTOs, interfaces) and persistence code live in reusable components such as `components/bot_detector/structs` and `components/bot_detector/database`, so every base/project imports the same contracts and models without circular dependencies. Use the `structs` naming everywhere (no `schemas` leftovers) and suffix types consistently (`FooInput`, `FooResponse`, etc.).
- **Tests** live under the workspace-level `test/` directory via `[tool.polylith.test]`, so base/component fixtures and contract tests should be added there rather than inside each brick folder. Add per-base `resources/` directories only when a base needs static assets or config that isn’t shared elsewhere.

# The Polylith Architecture
## Overview
The Polylith architecture is a modular approach to organizing codebases, aimed at improving maintainability, reducing duplication, and providing better oversight of projects. It is particularly well-suited for managing large, complex applications.

### Why Use Polylith?
1. **Reduce Duplication**: With many repositories, schemas and functionalities are often replicated, leading to inconsistencies and maintenance challenges. Polylith consolidates shared code into reusable components.
2. **Improve Oversight**: Managing multiple repositories can obscure the overall project structure. Polylith centralizes the architecture, making it easier to navigate and understand.
3. **Streamline Onboarding**: New developers can quickly understand the project structure without needing to navigate numerous repositories.

## Documentation
For an in-depth guide on Polylith architecture, visit the [Polylith Documentation](https://davidvujic.github.io/python-polylith-docs/).

## Commands
Below are the essential commands for working with Polylith in your project.

### Create a Base
A base serves as the foundation for your architecture, often containing shared logic or configurations.

```sh
uv run poly create base --name <base_name>
```
### Create a Component
A component is a reusable, self-contained module that encapsulates specific functionality.
```sh
uv run poly create component --name <component_name>
```

### Create a Project
A project is the entry point for your application, built using the base and components.
```sh
uv run poly create project --name <project_name>
```
# design

```mermaid
flowchart TD
    subgraph Ingestion
        JavaPlugin(Java Plugin)
        PublicAPI(Public API)
        JavaPlugin --> PublicAPI
        PublicAPI --> KafkaReports[/"Kafka: reports.to_insert"/]
    end

    subgraph Scheduling
        TaskScheduler(Task Scheduler)
        TaskScheduler --> KafkaToScrape[/"Kafka: players.to_scrape"/]
    end

    subgraph Scraping
        KafkaToScrape --> HighscoreScraper(Highscore Scraper)
        HighscoreScraper --> KafkaNotFound[/"Kafka: players.not_found"/]
        HighscoreScraper --> KafkaScraped[/"Kafka: players.scraped"/]
        KafkaNotFound --> RunemetricsScraper(Runemetrics Scraper)
        RunemetricsScraper --> KafkaScraped
    end

    subgraph Processing
        KafkaScraped --> HighscoreWorker(Highscore Worker)
        HighscoreWorker --> KafkaForML[/"Kafka: players.to_score"/]
    end

    subgraph ML
        KafkaForML --> MLServing(ML-Serving)
        MLServing --> KafkaPredictions[/"Kafka: players.scored"/]
    end

    subgraph Storage
        KafkaPredictions --> PredictionWorker(Prediction Worker)
        KafkaReports --> ReportWorker(Report Worker)

        HighscoreWorker --> MySQL[(MySQL)]
        PredictionWorker --> MySQL[(MySQL)]
        ReportWorker --> MySQL[(MySQL)]
    end
```
# intersting commands
```sh
find . -type f -name "pyproject.toml" -not -path "*/.venv/*" -execdir sh -c 'echo "🔄 Updating lock in $(pwd)"; uv lock' \;
```
# syncing in all directories, so uv cache is setup
```sh
find . -type f -name "pyproject.toml" -not -path "*/.venv/*" -execdir sh -c 'echo "🔄 syncing in $(pwd)"; uv sync' \;
```
