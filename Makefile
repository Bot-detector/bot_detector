.PHONY: clean-test clean-pyc restart test test-verbose restart-service_name* setup docs
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

UNAME_S := $(shell uname -m)
DOCKER_ENV :=
ifeq ($(UNAME_S),arm64)
DOCKER_ENV = DOCKER_DEFAULT_PLATFORM=linux/amd64
endif

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

uv-cache:
	docker volume inspect uv_cache >/dev/null 2>&1 || docker volume create uv_cache

dev-restart: ## restart containers
	$(DOCKER_ENV) docker compose -f 'docker-compose-dev.yml' down
	$(DOCKER_ENV) docker compose -f 'docker-compose-dev.yml' up -d --build

restart: uv-cache## restart containers
	$(DOCKER_ENV) docker compose -f 'docker-compose.yml' down
	$(DOCKER_ENV) docker compose -f 'docker-compose.yml' up -d --build

test: restart ## restart containers & test
	uv run pytest
	
test-verbose: restart ## restart containers & test
	uv run pytest -s

restart-%: ## Restart a docker service by name, eg make restart-api_public
	uv sync --project projects/$*
	$(DOCKER_ENV) docker compose stop $*
	$(DOCKER_ENV) docker compose build $*
	$(DOCKER_ENV) docker compose up -d $*

setup:
	uv sync

docs: ## opens your browser to the webapps testing docs
	open http://localhost:5000/docs
	xdg-open http://localhost:5000/docs
	. http://localhost:5000/docs
opencode:
<<<<<<< Updated upstream
	docker compose -f docker-compose-oc.yml down
	docker compose -f docker-compose-oc.yml run --rm --build opencode
=======
	docker compose -f docker-compose.opencode.yml run --rm opencode
>>>>>>> Stashed changes
