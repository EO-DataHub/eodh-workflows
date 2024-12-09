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

INDEX=ndvi

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
	docker run -it \
		--name $(CONTAINER_NAME) $(IMAGE_NAME) \
		/bin/bash

.PHONY: docker-stop ## Stop Docker container
docker-stop:
	@echo "Stopping Docker container..."
	@if [ "$(shell docker ps -q -f name=$(CONTAINER_NAME))" ]; then \
		docker stop $(CONTAINER_NAME); \
		echo "Docker container $(CONTAINER_NAME) stopped."; \
	else \
		echo "Docker container $(CONTAINER_NAME) does not exist or is not running."; \
	fi

.PHONY: docker-rm  ## Remove Docker container
docker-rm:
	@echo "Removing Docker container..."
	@if [ "$(shell docker ps -a -q -f name=$(CONTAINER_NAME))" ]; then \
		docker rm $(CONTAINER_NAME); \
		echo "Docker container $(CONTAINER_NAME) removed."; \
	else \
		echo "Docker container $(CONTAINER_NAME) does not exist."; \
	fi

.PHONY: docker-rmi  ## Remove Docker image
docker-rmi:
	@echo "Removing Docker image..."
	@if [ "$(shell docker images -q $(IMAGE_NAME))" ]; then \
		docker rmi $(IMAGE_NAME); \
		echo "Docker image $(IMAGE_NAME) removed."; \
	else \
		echo "Docker image $(IMAGE_NAME) does not exist."; \
	fi

.PHONY: docker-prune  ## Clean build cache
docker-prune:
	@echo "Cleaning build cache..."
	docker builder prune --force

.PHONY: docker-clean  ## Clean up everything (container and image)
docker-clean: docker-stop docker-rm docker-rmi docker-prune

.PHONY: docker-rebuild  ## Rebuild and rerun Docker container
docker-rebuild: docker-stop docker-rm docker-rmi docker-all

# Command line execution commands

.PHONY: query-s2 ## Query Sentinel-2
query-s2:
	eopro ds query \
	--stac_collection sentinel-2-l2a \
	--area "{\"type\":\"Polygon\",\"coordinates\":[[[71.57683969558222,4.278154706539496],[71.96061157730237,4.278154706539496],[71.96061157730237,4.62344048537264],[71.57683969558222,4.62344048537264],[71.57683969558222,4.278154706539496]]]}" \
	--date_start 2024-01-01T00:00:00Z \
	--date_end 2024-12-31T23:59:59Z \
	--output_dir "./data/processed/eopro/ds-query/s2"

.PHONY: clip-s2 ## Works after query-s2
clip-s2:
	eopro raster clip \
	--input_stac "./data/processed/eopro/ds-query/s2" \
	--area "{\"type\":\"Polygon\",\"coordinates\":[[[71.65,4.35],[71.8,4.35],[71.8,4.5],[71.65,4.5],[71.65,4.35]]]}" \
	--output_dir "./data/processed/eopro/raster-clip/s2"

.PHONY: query-globallc ## Query ESA Global LC
query-globallc:
	eopro ds query \
 	--stac_collection esa-lccci-glcm \
	--area "{\"type\": \"Polygon\",\"coordinates\": [[[14.763294437090849, 50.833598186651244],[15.052268923898112, 50.833598186651244],[15.052268923898112, 50.989077215056824],[14.763294437090849, 50.989077215056824],[14.763294437090849, 50.833598186651244]]]}" \
	--date_start 2008-01-01T00:00:00Z \
	--date_end 2010-12-31T23:59:59Z \
	--output_dir "./data/processed/eopro/ds-query/esa-lccci-glcm"

.PHONY: clip-globallc ## Works after query-globallc
clip-globallc:
	eopro raster clip \
 	--input_stac "./data/processed/eopro/ds-query/esa-lccci-glcm" \
	--area "{\"type\": \"Polygon\",\"coordinates\": [[[15.0, 50.9],[15.03, 50.9],[15.03, 50.95],[15.0, 50.95],[15.0, 50.9]]]}" \
	--output_dir "./data/processed/eopro/raster-clip/esa-lccci-glcm"

.PHONY: lulc-change-globallc ## Works after query-globallc or clip-globallc
lulc-change-globallc:
	eopro classification summarize \
	--input_stac "./data/processed/eopro/raster-clip/esa-lccci-glcm" \
	--output_dir "./data/processed/eopro/classification-summarize/esa-lccci-glcm"

.PHONY: query-corine ## Query CORINE Land Cover
query-corine:
	eopro ds query \
 	--stac_collection clms-corine-lc \
	--area "{\"type\": \"Polygon\",\"coordinates\": [[[14.763294437090849, 50.833598186651244],[15.052268923898112, 50.833598186651244],[15.052268923898112, 50.989077215056824],[14.763294437090849, 50.989077215056824],[14.763294437090849, 50.833598186651244]]]}" \
	--date_start 2006-01-01T00:00:00Z \
	--date_end 2018-12-31T23:59:59Z \
	--output_dir "./data/processed/eopro/ds-query/corine"

.PHONY: lulc-change-corine ## Works after query-corine
lulc-change-corine:
	eopro classification summarize \
	--input_stac "./data/processed/eopro/ds-query/corine" \
	--output_dir "./data/processed/eopro/classification-summarize/corine"

.PHONY: query-wb ## Query Water Bodies
query-wb:
	eopro ds query \
	--stac_collection clms-water-bodies \
	--area "{\"type\": \"Polygon\",\"coordinates\": [[[14.82449, 50.99583],[14.82449, 51.15208],[15.09065, 51.15208],[15.09065, 50.99583],[14.82449, 50.99583]]]}" \
	--date_start 2024-01-01T00:00:00Z \
	--date_end 2024-03-31T23:59:59Z \
	--output_dir "./data/processed/eopro/ds-query/water-bodies"

.PHONY: lulc-change-wb ## Works after query-wb
lulc-change-wb:
	eopro classification summarize \
	--input_stac "./data/processed/eopro/ds-query/water-bodies" \
	--output_dir "./data/processed/eopro/classification-summarize/water-bodies"

# CWL workflow execution commands

.PHONY: cwl-ndvi  ## Runs Raster Calculator
cwl-raster-calculator:
	@cwltool ./cwl_files/local/raster-calculate-app.cwl\#raster-calculate \
		--stac_collection sentinel-2-l2a \
		--aoi "{\"type\":\"Polygon\",\"coordinates\":[[[71.57683969558222,4.278154706539496],[71.96061157730237,4.278154706539496],[71.96061157730237,4.62344048537264],[71.57683969558222,4.62344048537264],[71.57683969558222,4.278154706539496]]]}" \
		--date_start 2024-01-01T00:00:00Z \
		--date_end 2024-12-31T23:59:59Z \
		--limit=2 \
		--index=$(INDEX) \
		--clip=True

.PHONY: cwl-corinelc  ## Runs LULC Change with CORINE
cwl-corinelc:
	@cwltool ./cwl_files/local/lulc-change-app.cwl\#land-cover-change \
		--source clms-corinelc \
		--aoi "{\"type\": \"Polygon\",\"coordinates\": [[[14.763294437090849, 50.833598186651244],[15.052268923898112, 50.833598186651244],[15.052268923898112, 50.989077215056824],[14.763294437090849, 50.989077215056824],[14.763294437090849, 50.833598186651244]]]}" \
		--date_start 2006-01-01T00:00:00Z \
		--date_end 2018-12-31T23:59:59Z

.PHONY: cwl-globallc  ## Runs LULC Change with ESA GLC
cwl-globallc:
	@cwltool ./cwl_files/local/lulc-change-app.cwl\#land-cover-change \
		--source esacci-globallc \
		--aoi "{\"type\": \"Polygon\",\"coordinates\": [[[14.763294437090849, 50.833598186651244],[15.052268923898112, 50.833598186651244],[15.052268923898112, 50.989077215056824],[14.763294437090849, 50.989077215056824],[14.763294437090849, 50.833598186651244]]]}" \
		--date_start 2008-01-01T00:00:00Z \
		--date_end 2010-12-31T23:59:59Z

.PHONY: cwl-water-bodies  ## Runs LULC Change with Water Bodies
cwl-water-bodies:
	@cwltool ./cwl_files/local/lulc-change-app.cwl\#land-cover-change \
		--source clms-water-bodies \
		--aoi "{\"type\": \"Polygon\",\"coordinates\": [[[14.763294437090849, 50.833598186651244],[15.052268923898112, 50.833598186651244],[15.052268923898112, 50.989077215056824],[14.763294437090849, 50.989077215056824],[14.763294437090849, 50.833598186651244]]]}" \
		--date_start 2024-01-01T00:00:00Z \
		--date_end 2024-03-31T23:59:59Z

.PHONY: cwl-water-quality  ## Runs Water Quality app
cwl-water-quality:
	@cwltool ./cwl_files/local/water-quality-app.cwl\#water-quality \
		--stac_collection sentinel-2-l2a \
		--aoi "{\"type\":\"Polygon\",\"coordinates\":[[[71.57683969558222,4.278154706539496],[71.96061157730237,4.278154706539496],[71.96061157730237,4.62344048537264],[71.57683969558222,4.62344048537264],[71.57683969558222,4.278154706539496]]]}" \
		--date_start 2024-01-01T00:00:00Z \
		--date_end 2024-12-31T23:59:59Z \
		--limit=5 \
		--clip=True
