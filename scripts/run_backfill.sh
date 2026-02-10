#!/bin/bash
# Run backfill job for Zendesk tickets

set -e

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

echo "Starting Zendesk backfill..."
echo "Project: $GCP_PROJECT_ID"

# Run backfill
python -m src.ingestion.backfill "$@"

echo "Backfill complete!"
