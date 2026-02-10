.PHONY: setup install dev test lint format clean docker-up docker-down

# Setup complete development environment
setup: install
	@echo "Creating .env from example..."
	@test -f .env || cp .env.example .env
	@echo "Setup complete! Edit .env with your credentials."

# Install dependencies
install:
	pip install -e ".[dev]"

# Run tests
test:
	pytest -v

test-cov:
	pytest --cov=src --cov-report=html

# Linting and formatting
lint:
	ruff check src tests

format:
	ruff format src tests
	ruff check --fix src tests

# Type checking
typecheck:
	mypy src

# Run API locally
api:
	uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

# Run Streamlit UI locally
ui:
	streamlit run src/ui/app.py

# Docker commands
docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

docker-build:
	docker-compose build

# Clean up
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage

# BigQuery setup
bq-setup:
	python scripts/setup_bq.py

# Run backfill
backfill:
	python -m src.ingestion.backfill

# Run incremental ingestion
incremental:
	python -m src.ingestion.incremental
