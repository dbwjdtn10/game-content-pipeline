.PHONY: help install dev lint format type-check test test-cov up down logs clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

install: ## Install production dependencies
	pip install -e .

dev: ## Install dev dependencies (lint, test, type-check)
	pip install -e ".[dev]"

# ---------------------------------------------------------------------------
# Code Quality
# ---------------------------------------------------------------------------

lint: ## Run ruff linter
	ruff check src/ tests/

format: ## Auto-format code with ruff
	ruff format src/ tests/
	ruff check --fix src/ tests/

type-check: ## Run mypy type checker
	mypy src/ --ignore-missing-imports

# ---------------------------------------------------------------------------
# Testing
# ---------------------------------------------------------------------------

test: ## Run tests with coverage
	pytest tests/ -v --cov=src --cov-report=term-missing

test-cov: ## Run tests and generate HTML coverage report
	pytest tests/ -v --cov=src --cov-report=html
	@echo "Coverage report: htmlcov/index.html"

# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------

up: ## Start all services (PostgreSQL, Redis, Worker, API, Dashboard)
	docker compose up --build -d

down: ## Stop all services
	docker compose down

logs: ## Tail service logs
	docker compose logs -f

# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

run-demo: ## Run the demo pipeline via CLI
	gcpipe pipeline run --config demo_pipeline.yaml

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

clean: ## Remove build artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name htmlcov -exec rm -rf {} + 2>/dev/null || true
	rm -f coverage.xml .coverage
