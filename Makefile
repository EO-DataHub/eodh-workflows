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

IMAGE_NAME=eopro-workflows
CONTAINER_NAME=eopro-workflows
DOCKERFILE_PATH=.

INDEX=ndvi
CWL_FILES_DIR=./cwl_files/local
CWL_INPUTS_DIR=./cwl_files/inputs
CWL_OUTPUT_DIR=./data/processed/cwl

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
	@echo "Running docker system prune..."
	docker system prune -a --force

.PHONY: docker-clean  ## Clean up everything (container and image)
docker-clean: docker-stop docker-rm docker-rmi docker-prune

.PHONY: docker-rebuild  ## Rebuild and rerun Docker container
docker-rebuild: docker-stop docker-rm docker-rmi docker-all


# CWL workflow execution commands

.PHONY: cwl-ndvi  ## Runs Raster Calculator
cwl-ndvi:
	@cwltool \
		--tmp-outdir-prefix=$(CWL_OUTPUT_DIR)/rc-v1-ndvi/$(shell date --iso-8601=minutes)/tmp/ \
		--outdir=$(CWL_OUTPUT_DIR)/rc-v1-ndvi/$(shell date --iso-8601=minutes)/outputs/ \
		--leave-tmpdir \
		--copy-outputs \
		$(CWL_FILES_DIR)/eodh/raster-calculate-app.cwl\#raster-calculate \
		$(CWL_INPUTS_DIR)/raster-calculate/ndvi-s2.json


.PHONY: cwl-ard-ndvi  ## Runs Raster Calculator with S2 ARD
cwl-ard-ndvi:
	@cwltool \
		--tmp-outdir-prefix=$(CWL_OUTPUT_DIR)/rc-v1-ard-ndvi/$(shell date --iso-8601=minutes)/tmp/ \
		--outdir=$(CWL_OUTPUT_DIR)/rc-v1-ard-ndvi/$(shell date --iso-8601=minutes)/outputs/ \
		--leave-tmpdir \
		--copy-outputs \
		$(CWL_FILES_DIR)/eodh/raster-calculate-app.cwl\#raster-calculate \
		$(CWL_INPUTS_DIR)/raster-calculate/ndvi-ard.json


.PHONY: cwl-ard-doc  ## Runs Raster Calculator with S2 ARD
cwl-ard-doc:
	@cwltool \
		--tmp-outdir-prefix=$(CWL_OUTPUT_DIR)/rc-v1-ard-doc/$(shell date --iso-8601=minutes)/tmp/ \
		--outdir=$(CWL_OUTPUT_DIR)/rc-v1-ard-doc/$(shell date --iso-8601=minutes)/outputs/ \
		--leave-tmpdir \
		--copy-outputs \
		$(CWL_FILES_DIR)/eodh/raster-calculate-app.cwl\#raster-calculate \
		$(CWL_INPUTS_DIR)/raster-calculate/doc-ard.json


.PHONY: cwl-corinelc  ## Runs LULC Change with CORINE
cwl-corinelc:
	@cwltool \
		--tmp-outdir-prefix=$(CWL_OUTPUT_DIR)/lc-v1-corine/$(shell date --iso-8601=minutes)/tmp/ \
		--outdir=$(CWL_OUTPUT_DIR)/lc-v1-corine/$(shell date --iso-8601=minutes)/outputs/ \
		--leave-tmpdir \
		--copy-outputs \
		$(CWL_FILES_DIR)/eodh/lulc-change-app.cwl\#lulc-change \
		$(CWL_INPUTS_DIR)/land-cover-change/corine.json


.PHONY: cwl-globallc  ## Runs LULC Change with ESA GLC
cwl-globallc:
	@cwltool \
		--tmp-outdir-prefix=$(CWL_OUTPUT_DIR)/lc-v1-glc/$(shell date --iso-8601=minutes)/tmp/ \
		--outdir=$(CWL_OUTPUT_DIR)/lc-v1-glc/$(shell date --iso-8601=minutes)/outputs/ \
		--leave-tmpdir \
		--copy-outputs \
		$(CWL_FILES_DIR)/eodh/lulc-change-app.cwl\#lulc-change \
		$(CWL_INPUTS_DIR)/land-cover-change/globallc.json


.PHONY: cwl-water-bodies  ## Runs LULC Change with Water Bodies
cwl-water-bodies:
	@cwltool \
		--tmp-outdir-prefix=$(CWL_OUTPUT_DIR)/lc-v1-wb/$(shell date --iso-8601=minutes)/tmp/ \
		--outdir=$(CWL_OUTPUT_DIR)/lc-v1-wb/$(shell date --iso-8601=minutes)/outputs/ \
		--leave-tmpdir \
		--copy-outputs \
		$(CWL_FILES_DIR)/eodh/lulc-change-app.cwl\#lulc-change \
		$(CWL_INPUTS_DIR)/land-cover-change/water-bodies.json


.PHONY: cwl-water-quality  ## Runs Water Quality app
cwl-water-quality:
	@cwltool \
		--tmp-outdir-prefix=$(CWL_OUTPUT_DIR)/wq-v1/$(shell date --iso-8601=minutes)/tmp/ \
		--outdir=$(CWL_OUTPUT_DIR)/wq-v1/$(shell date --iso-8601=minutes)/outputs/ \
		--leave-tmpdir \
		--copy-outputs \
		$(CWL_FILES_DIR)/eodh/water-quality-app.cwl\#water-quality \
		$(CWL_INPUTS_DIR)/water-quality/s2.json


.PHONY: cwl-ard-wq  ## Runs Water Quality app with S2 ARD
cwl-ard-wq:
	@cwltool \
		--tmp-outdir-prefix=$(CWL_OUTPUT_DIR)/wq-v1-ard/$(shell date --iso-8601=minutes)/tmp/ \
		--outdir=$(CWL_OUTPUT_DIR)/wq-v1-ard/$(shell date --iso-8601=minutes)/outputs/ \
		--leave-tmpdir \
		--copy-outputs \
		$(CWL_FILES_DIR)/eodh/water-quality-app.cwl\#water-quality \
		$(CWL_INPUTS_DIR)/water-quality/ard.json

# CWL V2 commands

.PHONY: v2-cwl-ndvi-simple  ## Runs Simple NDVI WF (V2)
v2-cwl-ndvi-simple:
	cwltool \
		--tmp-outdir-prefix=$(CWL_OUTPUT_DIR)/ndvi-simple/$(shell date --iso-8601=minutes)/tmp/ \
		--tmpdir-prefix=$(CWL_OUTPUT_DIR)/ndvi-simple/$(shell date --iso-8601=minutes)/tmp/ \
		--outdir=$(CWL_OUTPUT_DIR)/ndvi-simple/$(shell date --iso-8601=minutes)/outputs/ \
		--leave-tmpdir \
		--copy-outputs \
		$(CWL_FILES_DIR)/eopro/simplest-ndvi.cwl\#simplest-ndvi \
		--area "{\"type\":\"Polygon\",\"coordinates\":[[[-2.652110837830426,51.31487834129703],[-2.5885590161086514,51.31487834129703],[-2.5885590161086514,51.35420103894873],[-2.652110837830426,51.35420103894873],[-2.652110837830426,51.31487834129703]]]}" \
		--dataset sentinel-2-l2a-ard \
		--date_start 2023-03-01 \
		--date_end 2024-10-10 \
		--query_clip True \
		--query_limit 2 \
		--query_cloud_cover_min 0 \
		--query_cloud_cover_max 100 \
		--ndvi_index ndvi

.PHONY: v2-cwl-ndvi-full  ## Runs Full NDVI WF (V2)
v2-cwl-ndvi-full:
	make docker-build
	cwltool \
		--tmp-outdir-prefix=$(CWL_OUTPUT_DIR)/ndvi-full/$(shell date --iso-8601=minutes)/tmp/ \
		--tmpdir-prefix=$(CWL_OUTPUT_DIR)/ndvi-full/$(shell date --iso-8601=minutes)/tmp/ \
		--outdir=$(CWL_OUTPUT_DIR)/ndvi-full/$(shell date --iso-8601=minutes)/outputs/ \
		--leave-tmpdir \
		--copy-outputs \
		$(CWL_FILES_DIR)/eopro/ndvi-clip-reproject.cwl\#ndvi-clip-repr \
		--area "{\"type\":\"Polygon\",\"coordinates\":[[[-2.652110837830426,51.31487834129703],[-2.5885590161086514,51.31487834129703],[-2.5885590161086514,51.35420103894873],[-2.652110837830426,51.35420103894873],[-2.652110837830426,51.31487834129703]]]}" \
		--dataset sentinel-2-l2a-ard \
		--date_start 2023-03-01 \
		--date_end 2024-10-10 \
		--query_clip True \
		--query_limit 2 \
		--query_cloud_cover_min 0 \
		--query_cloud_cover_max 100 \
		--ndvi_index ndvi \
		--reproject_epsg EPSG:3857

.PHONY: v2-cwl-wq  ## Runs WQ WF (V2)
v2-cwl-wq:
	cwltool \
		--tmp-outdir-prefix=$(CWL_OUTPUT_DIR)/wq/$(shell date --iso-8601=minutes)/tmp/ \
		--outdir=$(CWL_OUTPUT_DIR)/wq/$(shell date --iso-8601=minutes)/outputs/ \
		--leave-tmpdir \
		--copy-outputs \
		$(CWL_FILES_DIR)/eopro/water-quality.cwl\#water-quality-wf \
		--area "{\"type\":\"Polygon\",\"coordinates\":[[[-2.652110837830426,51.31487834129703],[-2.5885590161086514,51.31487834129703],[-2.5885590161086514,51.35420103894873],[-2.652110837830426,51.35420103894873],[-2.652110837830426,51.31487834129703]]]}" \
		--dataset sentinel-2-l2a-ard \
		--date_start 2023-03-01 \
		--date_end 2024-10-10 \
		--query_clip True \
		--query_limit 2 \
		--query_cloud_cover_min 0 \
		--query_cloud_cover_max 100 \
		--reproject_epsg EPSG:3857

.PHONY: v2-cwl-adv-wq  ## Runs Advanced WQ WF (V2)
v2-cwl-adv-wq:
	cwltool \
		--tmp-outdir-prefix=$(CWL_OUTPUT_DIR)/adv-wq/$(shell date --iso-8601=minutes)/tmp/ \
		--outdir=$(CWL_OUTPUT_DIR)/adv-wq/$(shell date --iso-8601=minutes)/outputs/ \
		--leave-tmpdir \
		--copy-outputs \
		$(CWL_FILES_DIR)/eopro/advanced-water-quality.cwl\#adv-wq \
		--area "{\"type\":\"Polygon\",\"coordinates\":[[[-2.652110837830426,51.31487834129703],[-2.5885590161086514,51.31487834129703],[-2.5885590161086514,51.35420103894873],[-2.652110837830426,51.35420103894873],[-2.652110837830426,51.31487834129703]]]}" \
		--dataset sentinel-2-l2a-ard \
		--date_start 2023-03-01 \
		--date_end 2024-10-10 \
		--query_clip True \
		--query_limit 2 \
		--query_cloud_cover_min 0 \
		--query_cloud_cover_max 100 \
		--ndwi_index ndwi \
		--reproject_ndwi EPSG:3857 \
		--cya_index cya_cells \
		--reproject_cya_epsg EPSG:3857 \
		--doc_index doc \
		--reproject_doc_epsg EPSG:3857 \
		--cdom_index cdom \
		--reproject_cdom_epsg EPSG:3857

.PHONY: v2-cwl-lc-glc  ## Runs LCC GLC WF (V2)
v2-cwl-lc-glc:
	cwltool \
		--tmp-outdir-prefix=$(CWL_OUTPUT_DIR)/lc-glc/$(shell date --iso-8601=minutes)/tmp/ \
		--outdir=$(CWL_OUTPUT_DIR)/lc-glc/$(shell date --iso-8601=minutes)/outputs/ \
		--leave-tmpdir \
		--copy-outputs \
 		$(CWL_FILES_DIR)/eopro/land-cover.cwl\#lcc \
		--area "{\"type\": \"Polygon\", \"coordinates\": [[[-0.511790994620525, 51.44563991163383], [-0.511790994620525, 51.496989653093614], [-0.408954489023431, 51.496989653093614], [-0.408954489023431, 51.44563991163383], [-0.511790994620525, 51.44563991163383]]]}" \
		--dataset esa-lccci-glcm \
		--date_start 1994-01-01 \
		--date_end 2015-12-31 \
		--query_limit 2 \
		--query_clip True \
		--reproject_epsg EPSG:3857

.PHONY: v2-cwl-lc-corine  ## Runs LCC Corine WF (V2)
v2-cwl-lc-corine:
	cwltool \
		--tmp-outdir-prefix=$(CWL_OUTPUT_DIR)/lc-corine/$(shell date --iso-8601=minutes)/tmp/ \
		--outdir=$(CWL_OUTPUT_DIR)/lc-corine/$(shell date --iso-8601=minutes)/outputs/ \
		--leave-tmpdir \
		--copy-outputs \
 		$(CWL_FILES_DIR)/eopro/land-cover.cwl\#lcc \
		--area "{\"type\":\"Polygon\",\"coordinates\":[[[14.71116464777238,50.841106893082866],[15.07930529622954,50.841106893082866],[15.07930529622954,51.11754967134041],[14.71116464777238,51.11754967134041],[14.71116464777238,50.841106893082866]]]}" \
		--dataset clms-corine-lc \
		--date_start 1980-01-01 \
		--date_end 2020-12-31 \
		--query_limit 20 \
		--query_clip True \
		--reproject_epsg EPSG:3857

.PHONY: v2-cwl-s2ard-ndvi  ## Runs NDVI S2 ARD WF (V2)
v2-cwl-s2ard-ndvi:
	cwltool \
		--tmp-outdir-prefix=$(CWL_OUTPUT_DIR)/ndvi-full-adr/$(shell date --iso-8601=minutes)/tmp/ \
		--outdir=$(CWL_OUTPUT_DIR)/ndvi-full-adr/$(shell date --iso-8601=minutes)/outputs/ \
		--leave-tmpdir \
		--copy-outputs \
		$(CWL_FILES_DIR)/eopro/ndvi-clip-reproject.cwl\#ndvi-clip-repr \
		--area "{\"type\": \"Polygon\", \"coordinates\": [[[-0.511790994620525, 51.44563991163383], [-0.511790994620525, 51.496989653093614], [-0.408954489023431, 51.496989653093614], [-0.408954489023431, 51.44563991163383], [-0.511790994620525, 51.44563991163383]]]}" \
		--dataset sentinel-2-l2a-ard \
		--date_start 2023-01-01 \
		--date_end 2024-10-10 \
		--query_clip True \
		--query_limit 2 \
		--query_cloud_cover_min 0 \
		--query_cloud_cover_max 100 \
		--ndvi_index ndvi \
		--reproject_epsg EPSG:3857

.PHONY: v2-cwl-s2ard-wq  ## Runs WQ S2 ARD WF (V2)
v2-cwl-s2ard-wq:
	cwltool \
		--tmp-outdir-prefix=$(CWL_OUTPUT_DIR)/wq-adr/$(shell date --iso-8601=minutes)/tmp/ \
		--outdir=$(CWL_OUTPUT_DIR)/wq-adr/$(shell date --iso-8601=minutes)/outputs/ \
		--leave-tmpdir \
		--copy-outputs \
		$(CWL_FILES_DIR)/eopro/water-quality.cwl\#water-quality-wf \
		--area "{\"type\":\"Polygon\",\"coordinates\":[[[-2.5962507170463245,55.15651250330746],[-2.4458753508353874,55.15651250330746],[-2.4458753508353874,55.23019781679735],[-2.5962507170463245,55.23019781679735],[-2.5962507170463245,55.15651250330746]]]}" \
		--dataset sentinel-2-l2a-ard \
		--date_start 2023-01-01 \
		--date_end 2024-12-10 \
		--query_clip True \
		--query_limit 2 \
		--query_cloud_cover_min 0 \
		--query_cloud_cover_max 100 \
		--reproject_epsg EPSG:3857

.PHONY: cwl-v1  ## Run CWL apps V1
cwl-v1: docker-build cwl-ard-ndvi cwl-ard-doc cwl-corinelc cwl-globallc cwl-water-bodies cwl-ard-wq cwl-scatter-wq

.PHONY: cwl-v2  ## Run CWL apps V2
cwl-v2: docker-build v2-cwl-ndvi-simple v2-cwl-ndvi-full v2-cwl-wq v2-cwl-adv-wq v2-cwl-lc-corine v2-cwl-lc-glc v2-cwl-s2ard-ndvi v2-cwl-s2ard-wq

.PHONY: cwl-all  ## Run ALL CWL apps
cwl-all: cwl-v1 cwl-v2

.PHONY: cwl-scatter-wq  ## Runs Scatter WQA
cwl-scatter-wq:
	@cwltool \
		--tmp-outdir-prefix=$(CWL_OUTPUT_DIR)/scatter-wq/$(shell date --iso-8601=minutes)/tmp/ \
		--outdir=$(CWL_OUTPUT_DIR)/scatter-wq/$(shell date --iso-8601=minutes)/outputs/ \
		--leave-tmpdir \
		--copy-outputs \
		$(CWL_FILES_DIR)/eodh/scatter-water-quality-app.cwl\#scatter-water-quality \
		$(CWL_INPUTS_DIR)/water-quality/scatter-ard.json

.PHONY: cwl-scatter-rc-ndvi  ## Runs Scatter RC NDVI
cwl-scatter-rc-ndvi:
	@cwltool \
		--tmp-outdir-prefix=$(CWL_OUTPUT_DIR)/scatter-rc-ndvi/$(shell date --iso-8601=minutes)/tmp/ \
		--outdir=$(CWL_OUTPUT_DIR)/scatter-rc-ndvi/$(shell date --iso-8601=minutes)/outputs/ \
		--leave-tmpdir \
		--copy-outputs \
		$(CWL_FILES_DIR)/scatter-raster-calcluate-app.cwl\#scatter-raster-calculate \
		$(CWL_INPUTS_DIR)/raster-calcluate/scatter-ndvi.json

.PHONY: cwl-scatter-rc-cya  ## Runs Scatter RC CYA
cwl-scatter-rc-cya:
	@cwltool \
		--tmp-outdir-prefix=$(CWL_OUTPUT_DIR)/scatter-rc-cya/$(shell date --iso-8601=minutes)/tmp/ \
		--outdir=$(CWL_OUTPUT_DIR)/scatter-rc-cya/$(shell date --iso-8601=minutes)/outputs/ \
		--leave-tmpdir \
		--copy-outputs \
		$(CWL_FILES_DIR)/scatter-raster-calculate-app.cwl\#scatter-raster-calculate \
		$(CWL_INPUTS_DIR)/raster-calculate/scatter-cya.json

.PHONY: cwl-scatter-lcc  ## Runs Scatter LCC
cwl-scatter-lcc:
	@cwltool \
		--tmp-outdir-prefix=$(CWL_OUTPUT_DIR)/scatter-lcc/$(shell date --iso-8601=minutes)/tmp/ \
		--outdir=$(CWL_OUTPUT_DIR)/scatter-lcc/$(shell date --iso-8601=minutes)/outputs/ \
		--leave-tmpdir \
		--copy-outputs \
		$(CWL_FILES_DIR)/scatter-lulc-change-app.cwl\#scatter-lulc-change \
		$(CWL_INPUTS_DIR)/land-cover-change/scatter-corine.json
