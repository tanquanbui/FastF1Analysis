.PHONY: help install test test-ingestion test-processor test-api test-fingerprint test-trainer test-predictor test-all lint format build deploy deploy-prod sync invoke-ingestion invoke-processor seed-historical clean preflight validate compile-check tree

help:
	@echo "PitStop Analytics — make targets"
	@echo ""
	@echo "  preflight          Run all pre-deploy checks (compile + test + sam validate)"
	@echo "  install            Install dev dependencies for all functions"
	@echo "  compile-check      Syntax-check every Python file"
	@echo "  validate           sam validate --lint"
	@echo "  test               Run Phase 1 unit tests"
	@echo "  test-all           Run Phase 1 + Phase 2 unit tests"
	@echo "  test-ingestion     Run ingestion Lambda tests"
	@echo "  test-processor     Run processor Lambda tests"
	@echo "  test-api           Run API Lambda tests"
	@echo "  test-fingerprint   Run fingerprint Lambda tests"
	@echo "  test-trainer       Run trainer Lambda tests"
	@echo "  test-predictor     Run predictor Lambda tests"
	@echo "  lint               Run ruff + black checks"
	@echo "  format             Auto-format with black"
	@echo "  build              sam build"
	@echo "  deploy             sam deploy (dev)"
	@echo "  deploy-prod        sam deploy --config-env prod"
	@echo "  sync               sam sync (watch mode)"
	@echo "  invoke-ingestion   Invoke ingestion locally with sample event"
	@echo "  invoke-processor   Invoke processor locally with sample event"
	@echo "  seed-historical    Backfill 2020-2024 race data"
	@echo "  tree               Show project tree (top 3 levels)"
	@echo "  clean              Remove caches and build artifacts"

install:
	pip install -r functions/ingestion/requirements.txt
	pip install -r functions/processor/requirements.txt
	pip install -r functions/api/requirements.txt
	pip install -r functions/fingerprint/requirements.txt
	pip install -r functions/trainer/requirements.txt
	pip install -r functions/predictor/requirements.txt
	pip install pytest pytest-cov moto ruff black

test: test-ingestion test-processor test-api
	@echo "All Phase 1 tests passed."

test-ingestion:
	cd functions/ingestion && python -m pytest

test-processor:
	cd functions/processor && python -m pytest

test-api:
	cd functions/api && python -m pytest

test-fingerprint:
	cd functions/fingerprint && python -m pytest

test-trainer:
	cd functions/trainer && python -m pytest

test-predictor:
	cd functions/predictor && python -m pytest

test-all: test test-fingerprint test-trainer test-predictor
	@echo "All tests passed (Phase 1 + Phase 2)."

lint:
	ruff check functions/ ml/ scripts/
	black --check functions/ ml/ scripts/

format:
	black functions/ ml/ scripts/
	ruff check --fix functions/ ml/ scripts/

build:
	sam build

deploy: build
	sam deploy

deploy-prod: build
	sam deploy --config-env prod

sync:
	sam sync --stack-name pitstop-analytics --watch

invoke-ingestion:
	sam local invoke IngestionFunction --event events/ingestion.json

invoke-processor:
	sam local invoke ProcessorFunction --event events/processor.json

seed-historical:
	python scripts/seed_historical.py

clean:
	rm -rf .aws-sam/
	rm -rf fastf1_cache/
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true

compile-check:
	@echo "==> Syntax-checking every Python file"
	@find functions ml scripts shared -name "*.py" -not -path "*/__pycache__/*" -print0 \
	  | xargs -0 -n1 python3 -m py_compile
	@echo "OK — every .py file compiles"

validate:
	@echo "==> sam validate --lint"
	@sam validate --lint

preflight: compile-check test-all validate
	@echo ""
	@echo "================================================================"
	@echo "  Preflight clean. Next:  make build && make deploy"
	@echo "================================================================"

tree:
	@find . -maxdepth 3 -type d -not -path "*/__pycache__*" -not -path "*/.aws-sam*" -not -path "*/.git*" | sort
