# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI-powered support assistant MVP for Zendesk integration. Analyzes support tickets, identifies intents via clustering, and generates response suggestions with confidence scores.

**Tech Stack:** Python 3.11+, FastAPI, Streamlit, BigQuery, Cloud Run, OpenAI (embeddings + generation), HDBSCAN/UMAP for clustering.

## Build & Development Commands

```bash
# Setup (once project structure is created)
make setup                    # Install dependencies and configure environment

# Running services locally
docker-compose up             # Run all services (API + UI + local PostgreSQL)
uvicorn src.api.main:app --reload  # Run API only
streamlit run src/ui/app.py   # Run Streamlit UI only

# Testing
pytest                        # Run all tests
pytest tests/test_ingestion/  # Run specific test module
pytest -k "test_cleaner"      # Run tests matching pattern

# Infrastructure
terraform -chdir=infra/terraform init
terraform -chdir=infra/terraform apply

# Data processing scripts
python scripts/setup_bq.py    # Initialize BigQuery tables
./scripts/run_backfill.sh     # Run Zendesk ticket backfill
python -m src.ingestion.backfill           # Run backfill directly
python -m src.ingestion.incremental        # Run incremental ingestion
python -m src.processing.pipeline          # Run cleaning pipeline
python -m src.processing.pipeline --qa-report  # Generate QA report

# Linting and formatting
make lint                     # Run ruff linter
make format                   # Format code with ruff
make typecheck                # Run mypy type checking
```

## Architecture

### Data Flow
1. **Ingestion** (`src/ingestion/`): Zendesk API → `raw_tickets` table (backfill + incremental)
2. **Processing** (`src/processing/`): Clean text, separate customer/agent messages, redact PII → `clean_tickets`
3. **Intents** (`src/intents/`): Generate embeddings → UMAP reduction → HDBSCAN clustering → scored intents
4. **Generation** (`src/generation/`): Intent detection + prompt selection + OpenAI generation → suggestions with confidence
5. **Feedback loop**: Agent accept/edit/reject → `feedback` table → metrics

### Key Directories
- `src/api/` - FastAPI endpoints (suggestions, feedback, metrics)
- `src/ui/` - Streamlit multi-page app (tickets view, dashboard, intents management)
- `prompts/` - System prompts and per-intent YAML templates with policies and few-shot examples
- `infra/` - Terraform configs, Dockerfiles, docker-compose

### BigQuery Tables
- `raw_tickets` → `clean_tickets` → `embeddings` → `clusters` → `intents` → `suggestions` → `feedback`

## Technical Guidelines

### Embeddings & Clustering
- Use `text-embedding-3-small` on customer messages only (not agent responses)
- UMAP: n_neighbors=15, min_dist=0.1, n_components=25 for clustering (2D only for visualization)
- HDBSCAN: min_cluster_size = max(20, 3% of dataset), min_samples=5
- Intent detection: find nearest centroid, if distance > threshold → no suggestion

### Confidence Scoring
- Normalize centroid distance to 0-1 scale
- Thresholds: >0.75 high, 0.5-0.75 medium, <0.5 don't suggest

### PII Handling
- Regex-based redaction for emails, Chilean phone numbers (+56 X XXXX XXXX), RUTs
- Validate with manual QA on sample of 100 tickets

### API Design
- Read-only for Zendesk (never auto-send responses)
- Cache generated suggestions (don't regenerate)
- API key authentication, CORS enabled
