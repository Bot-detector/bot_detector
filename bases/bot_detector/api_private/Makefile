.PHONY: clean clean-test clean-pyc clean-build build help
.DEFAULT_GOAL := help

define PRINT_HELP_PYSCRIPT
import re, sys

for line in sys.stdin:
	match = re.match(r'^([a-zA-Z_-]+):.*?## (.*)$$', line)
	if match:
		target, help = match.groups()
		print("%-20s %s" % (target, help))
endef
export PRINT_HELP_PYSCRIPT

help:
	@python3 -c "$$PRINT_HELP_PYSCRIPT" < $(MAKEFILE_LIST)

clean-pyc: ## clean python cache files
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -fr {} +
	find . -name '.pytest_cache' -exec rm -fr {} +

clean-test: ## cleanup pytests leftovers
	rm -f .coverage
	rm -fr htmlcov/
	rm -fr test_results/
	rm -f *report.html
	rm -f log.html
	rm -f test-results.html
	rm -f output.xml

test: clean ## Run pytest unit tests
	python3 -m pytest

test-debug: ## Run unit tests with debugging enabled
	python3 -m pytest --pdb

test-coverage: clean ## Run unit tests and check code coverage
	PYTHONPATH=src python3 -m pytest --cov=src tests/ --disable-warnings

docker-up: ## Startup docker
	docker-compose --verbose up

docker-build: ## Startup docker
	docker-compose --verbose up --build

setup: requirements pre-commit-setup docker-build test-setup api-setup ## setup & run after downloaded repo

pre-commit-setup: ## Install pre-commit
	python3 -m pip install pre-commit
	pre-commit --version

pre-commit: ## Run pre-commit
	pre-commit run --all-files

test-setup:
	python3 -m pip install pytest
	python3 -m pip install pytest-benchmark

list-benchmarks:
	pytest-benchmark list

benchmark:
	pytest tests/test_highscore_benchmark.py --benchmark-min-rounds=1000

create-venv:
	python3 -m venv .venv
	source .venv/bin/activate

requirements:
	python3 -m pip install -r requirements.txt
	python3 -m pip install pytest-asyncio==0.23.6
	python3 -m pip install httpx==0.27.0
	python3 -m pip install pre-commit==3.6.2
	python3 -m pip install ruff==0.1.15
	pre-commit install

docker-restart:
	docker compose down
	docker compose up --build -d

docker-test:
	docker compose down
	docker compose up --build -d
	pytest

api-setup:
	python3 -m pip install "fastapi[all]"

env-setup:
	touch .env
	echo "KAFKA_HOST= 'localhost:9092'" >> .env
	echo "DATABASE_URL= 'mysql+aiomysql://root:root_bot_buster@localhost:3307/playerdata'"  >> .env
	echo "ENV='DEV'" >> .env
	echo "POOL_RECYCLE='60'" >> .env
	echo "POOL_TIMEOUT='30'" >> .env

docs:
	open http://localhost:5000/docs
	xdg-open http://localhost:5000/docs
	. http://localhost:5000/docs
