.DEFAULT_GOAL := help
ruff-lint = ruff check --fix --preview .
ruff-format = ruff format --preview .
mypy = mypy .
pre-commit = pre-commit run --all-files

DATA_DIR=data
SHELL=/bin/bash
CONDA_ENV_NAME=eodh-workflows
# Note that the extra activate is needed to ensure that the activate floats env to the front of PATH
CONDA_ACTIVATE=source $$(conda info --base)/etc/profile.d/conda.sh ; conda activate ; conda activate $(CONDA_ENV_NAME)
CONDA_ACTIVATE_BASE=source $$(conda info --base)/etc/profile.d/conda.sh ; conda activate ; conda activate base

IMAGE_NAME=eodh-workflows
CONTAINER_NAME=eodh-workflows
DOCKERFILE_PATH=.

define PRINT_HELP_PYSCRIPT
import re, sys

for line in sys.stdin:
	match = re.match(r'^\.PHONY: ([0-9a-zA-Z_-]+).*?## (.*)$$', line)
	if match:
		target, help = match.groups()
		print("%-45s - %s" % (target, help))
endef
export PRINT_HELP_PYSCRIPT

.PHONY: help  ## Prints help message
help:
	@python -c "$$PRINT_HELP_PYSCRIPT" < $(MAKEFILE_LIST)

# Git repo initialization

.PHONY: git-init  ## Initializes Git repository
git-init:
	git init -b main
	git add .

# Freezing dependedncies

.PHONY: lock-file  ## Creates conda-lock file
lock-file:
	rm -rf conda-lock-dev.yml
	$(CONDA_ACTIVATE_BASE) ; conda-lock --mamba -f env.yaml -f env-dev.yaml --lockfile conda-lock-dev.yml
	git add conda-lock-dev.yml

.PHONY: release-lock-file  ## Creates conda-lock file without dev dependencies - to be used for deployment
release-lock-file:
	rm -rf conda-lock.yml
	$(CONDA_ACTIVATE_BASE) ; conda-lock --mamba -f env.yaml --lockfile conda-lock.yml
	git add conda-lock.yml

# Environment creation

.PHONY: conda-lock-install  ## Creates env from conda-lock file
conda-lock-install:
	$(CONDA_ACTIVATE_BASE) ; conda-lock install --mamba -n $(CONDA_ENV_NAME) conda-lock-dev.yml

.PHONY: setup-pre-commit  ## Installs pre-commit hooks
setup-pre-commit:
	$(CONDA_ACTIVATE) ; pre-commit install

.PHONY: setup-editable  ## Installs the project in an editable mode
setup-editable:
	$(CONDA_ACTIVATE) ; pip install -e .

.PHONY: env  ## Creates local environment and installs pre-commit hooks
env: conda-lock-install setup-pre-commit setup-editable

.PHONY: remove-env  ## Removes current conda environment
remove-env:
	$(CONDA_ACTIVATE_BASE) ; conda env remove -n $(CONDA_ENV_NAME)

.PHONY: recreate-env  ## Recreates conda environment by making new one from fresh lockfile
recreate-env: remove-env lock-file env

# Project initialization

.PHONY: init-project  ## Runs Git init, lock-file creation and env setup - to be used after cookiecutter initialization
init-project: git-init lock-file env

# Helpers

.PHONY: format  ## Runs code formatting (ruff)
format:
	$(ruff-lint)
	$(ruff-format)

.PHONY: type-check  ## Runs type checking with mypy
type-check:
	pre-commit run --all-files mypy

.PHONY: test  ## Runs pytest
test:
	pytest -v tests/

.PHONY: testcov  ## Runs tests and generates coverage reports
testcov:
	@rm -rf htmlcov
	pytest -v --cov-report html --cov-report xml --cov=$(CONDA_ENV_NAME) tests/

.PHONY: mpc  ## Runs manual pre-commit stuff
mpc: format type-check test

.PHONY: docs  ## Build the documentation
docs:
	mkdocs build

.PHONY: pc  ## Runs pre-commit hooks
pc:
	$(pre-commit)

.PHONY: clean  ## Cleans artifacts
clean:
	rm -rf `find . -name __pycache__`
	rm -f `find . -type f -name '*.py[co]' `
	rm -f `find . -type f -name '*~' `
	rm -f `find . -type f -name '.*~' `
	rm -rf .cache
	rm -rf flame
	rm -rf htmlcov
	rm -rf .pytest_cache
	rm -rf *.egg-info
	rm -f .coverage
	rm -f .coverage.*
	rm -f coverage.*
	rm -rf build
	rm -rf perf.data*
	rm -rf eodh-workflows/*.so
	rm -rf .mypy_cache
	rm -rf .benchmark
	rm -rf .hypothesis
	rm -rf docs-site

# Dockerfile commands

.PHONY: docker-all  ## Docker default target
docker-all: docker-build docker-run

.PHONY: docker-build  ## Build Docker image - builds image and runs Docker container
docker-build:
	@echo "Building Docker image..."
	docker build -t $(IMAGE_NAME) $(DOCKERFILE_PATH)

.PHONY: docker-run  ## Run Docker container
docker-run:
	@echo "Running Docker container..."
	docker run -d --name $(CONTAINER_NAME) $(IMAGE_NAME)

.PHONY: docker-stop  ## Stop Docker container
docker-stop:
	@echo "Stopping Docker container..."
	docker stop $(CONTAINER_NAME)

.PHONY: docker-rm  ## Remove Docker container
docker-rm:
	@echo "Removing Docker container..."
	docker rm $(CONTAINER_NAME)

.PHONY: docker-rmi  ## Remove Docker image
docker-rmi:
	@echo "Removing Docker image..."
	docker rmi $(IMAGE_NAME)

.PHONY: docker-clean  ## Clean up everything (container and image)
docker-clean: docker-stop docker-rm docker-rmi

.PHONY: docker-rebuild  ## Rebuild and rerun Docker container
docker-rebuild: docker-clean docker-all
