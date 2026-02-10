#!/usr/bin/env python3
"""Backfill job for ingesting historical tickets from Zendesk to BigQuery."""

import json
from datetime import datetime
from pathlib import Path

import structlog
from google.cloud import bigquery

from src.config import get_settings
from src.ingestion.zendesk_client import Ticket, ZendeskClient

logger = structlog.get_logger()

CHECKPOINT_FILE = Path("checkpoints/backfill_cursor.json")
BATCH_SIZE = 100


def load_checkpoint() -> str | None:
    """Load the last checkpoint cursor."""
    if CHECKPOINT_FILE.exists():
        data = json.loads(CHECKPOINT_FILE.read_text())
        return data.get("cursor")
    return None


def save_checkpoint(cursor: str | None, tickets_processed: int) -> None:
    """Save checkpoint with cursor and progress."""
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_FILE.write_text(
        json.dumps({
            "cursor": cursor,
            "tickets_processed": tickets_processed,
            "last_updated": datetime.utcnow().isoformat(),
        })
    )


def insert_tickets_to_bq(
    client: bigquery.Client,
    table_id: str,
    tickets: list[Ticket],
) -> None:
    """Insert a batch of tickets into BigQuery."""
    rows = [ticket.to_bq_row() for ticket in tickets]

    errors = client.insert_rows_json(table_id, rows)
    if errors:
        logger.error("BigQuery insert errors", errors=errors[:5])
        raise Exception(f"Failed to insert rows: {errors}")

    logger.info("Inserted tickets to BigQuery", count=len(rows))


def run_backfill(
    start_time: datetime | None = None,
    resume: bool = True,
    limit: int | None = None,
) -> dict[str, int]:
    """
    Run the backfill job to ingest historical tickets.

    Args:
        start_time: Optional start time for the backfill. If not provided and
                   resume=True, will resume from last checkpoint.
        resume: Whether to resume from the last checkpoint.
        limit: Optional limit on number of tickets to ingest.

    Returns:
        Dict with processing statistics.
    """
    settings = get_settings()
    table_id = f"{settings.gcp_project_id}.raw.tickets"

    # Load checkpoint if resuming
    cursor = None
    if resume:
        cursor = load_checkpoint()
        if cursor:
            logger.info("Resuming from checkpoint", cursor=cursor[:20] + "...")

    bq_client = bigquery.Client(project=settings.gcp_project_id)

    batch: list[Ticket] = []
    total_processed = 0
    last_cursor = cursor

    with ZendeskClient() as zd_client:
        logger.info(
            "Starting backfill",
            start_time=start_time.isoformat() if start_time else None,
            resume_cursor=cursor is not None,
        )

        for ticket, next_cursor in zd_client.iter_tickets(
            start_time=start_time,
            cursor=cursor,
        ):
            batch.append(ticket)
            last_cursor = next_cursor

            if len(batch) >= BATCH_SIZE:
                insert_tickets_to_bq(bq_client, table_id, batch)
                total_processed += len(batch)
                save_checkpoint(last_cursor, total_processed)
                logger.info(
                    "Progress",
                    total_processed=total_processed,
                    current_ticket_id=ticket.ticket_id,
                )
                batch = []

                # Check limit
                if limit and total_processed >= limit:
                    logger.info("Reached limit", limit=limit)
                    break

        # Insert remaining tickets
        if batch:
            insert_tickets_to_bq(bq_client, table_id, batch)
            total_processed += len(batch)
            save_checkpoint(last_cursor, total_processed)

    logger.info(
        "Backfill complete",
        total_tickets=total_processed,
    )

    return {"total_processed": total_processed}


def main() -> None:
    """CLI entry point for backfill."""
    import argparse

    parser = argparse.ArgumentParser(description="Backfill Zendesk tickets to BigQuery")
    parser.add_argument(
        "--start-date",
        type=str,
        help="Start date for backfill (YYYY-MM-DD). Defaults to 1 year ago.",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Don't resume from checkpoint, start fresh",
    )
    args = parser.parse_args()

    start_time = None
    if args.start_date:
        start_time = datetime.fromisoformat(args.start_date)

    run_backfill(start_time=start_time, resume=not args.no_resume)


if __name__ == "__main__":
    main()
