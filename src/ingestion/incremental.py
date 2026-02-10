#!/usr/bin/env python3
"""Incremental ingestion job for new/updated tickets from Zendesk."""

import json
from datetime import datetime, timedelta
from pathlib import Path

import structlog
from google.cloud import bigquery

from src.config import get_settings
from src.ingestion.zendesk_client import Ticket, ZendeskClient

logger = structlog.get_logger()

CURSOR_FILE = Path("checkpoints/incremental_cursor.json")
BATCH_SIZE = 50


def load_cursor() -> tuple[str | None, datetime | None]:
    """Load the last cursor and timestamp."""
    if CURSOR_FILE.exists():
        data = json.loads(CURSOR_FILE.read_text())
        last_run = data.get("last_run")
        return (
            data.get("cursor"),
            datetime.fromisoformat(last_run) if last_run else None,
        )
    return None, None


def save_cursor(cursor: str | None, last_run: datetime) -> None:
    """Save cursor and timestamp for next run."""
    CURSOR_FILE.parent.mkdir(parents=True, exist_ok=True)
    CURSOR_FILE.write_text(
        json.dumps({
            "cursor": cursor,
            "last_run": last_run.isoformat(),
        })
    )


def get_existing_ticket_ids(
    bq_client: bigquery.Client,
    project_id: str,
    ticket_ids: list[int],
) -> set[int]:
    """Check which ticket IDs already exist in BigQuery."""
    if not ticket_ids:
        return set()

    table_id = f"{project_id}.raw.tickets"
    ids_str = ",".join(str(tid) for tid in ticket_ids)

    query = f"""
        SELECT ticket_id
        FROM `{table_id}`
        WHERE ticket_id IN ({ids_str})
    """

    result = bq_client.query(query).result()
    return {row.ticket_id for row in result}


def upsert_tickets(
    bq_client: bigquery.Client,
    project_id: str,
    tickets: list[Ticket],
) -> tuple[int, int]:
    """
    Upsert tickets to BigQuery (insert new, update existing).

    Returns tuple of (inserted_count, updated_count).
    """
    if not tickets:
        return 0, 0

    table_id = f"{project_id}.raw.tickets"
    ticket_ids = [t.ticket_id for t in tickets]

    # Check which already exist
    existing_ids = get_existing_ticket_ids(bq_client, project_id, ticket_ids)

    new_tickets = [t for t in tickets if t.ticket_id not in existing_ids]
    updated_tickets = [t for t in tickets if t.ticket_id in existing_ids]

    # Insert new tickets
    if new_tickets:
        rows = [t.to_bq_row() for t in new_tickets]
        errors = bq_client.insert_rows_json(table_id, rows)
        if errors:
            logger.error("Insert errors", errors=errors[:5])

    # Update existing tickets using MERGE
    if updated_tickets:
        for ticket in updated_tickets:
            row = ticket.to_bq_row()
            # Use a MERGE statement to update
            query = f"""
                MERGE `{table_id}` T
                USING (SELECT @ticket_id as ticket_id) S
                ON T.ticket_id = S.ticket_id
                WHEN MATCHED THEN
                    UPDATE SET
                        subject = @subject,
                        description = @description,
                        comments_json = @comments_json,
                        updated_at = @updated_at,
                        tags = @tags,
                        channel = @channel,
                        assignee_id = @assignee_id,
                        status = @status,
                        priority = @priority,
                        requester_email = @requester_email,
                        ingested_at = @ingested_at
            """

            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("ticket_id", "INT64", row["ticket_id"]),
                    bigquery.ScalarQueryParameter("subject", "STRING", row["subject"]),
                    bigquery.ScalarQueryParameter("description", "STRING", row["description"]),
                    bigquery.ScalarQueryParameter("comments_json", "STRING", row["comments_json"]),
                    bigquery.ScalarQueryParameter("updated_at", "TIMESTAMP", row["updated_at"]),
                    bigquery.ArrayQueryParameter("tags", "STRING", row["tags"]),
                    bigquery.ScalarQueryParameter("channel", "STRING", row["channel"]),
                    bigquery.ScalarQueryParameter("assignee_id", "INT64", row["assignee_id"]),
                    bigquery.ScalarQueryParameter("status", "STRING", row["status"]),
                    bigquery.ScalarQueryParameter("priority", "STRING", row["priority"]),
                    bigquery.ScalarQueryParameter("requester_email", "STRING", row["requester_email"]),
                    bigquery.ScalarQueryParameter("ingested_at", "TIMESTAMP", row["ingested_at"]),
                ]
            )

            bq_client.query(query, job_config=job_config).result()

    logger.info(
        "Upsert complete",
        inserted=len(new_tickets),
        updated=len(updated_tickets),
    )

    return len(new_tickets), len(updated_tickets)


def run_incremental() -> None:
    """Run incremental ingestion for new/updated tickets."""
    settings = get_settings()
    bq_client = bigquery.Client(project=settings.gcp_project_id)

    # Load last run state
    cursor, last_run = load_cursor()

    # Default to 24 hours ago if no previous run
    if last_run is None:
        last_run = datetime.utcnow() - timedelta(days=1)

    logger.info(
        "Starting incremental ingestion",
        last_run=last_run.isoformat(),
        has_cursor=cursor is not None,
    )

    batch: list[Ticket] = []
    total_inserted = 0
    total_updated = 0
    last_cursor = cursor

    with ZendeskClient() as zd_client:
        for ticket, next_cursor in zd_client.iter_tickets(
            start_time=last_run,
            cursor=cursor,
        ):
            batch.append(ticket)
            last_cursor = next_cursor

            if len(batch) >= BATCH_SIZE:
                inserted, updated = upsert_tickets(
                    bq_client,
                    settings.gcp_project_id,
                    batch,
                )
                total_inserted += inserted
                total_updated += updated
                batch = []

        # Process remaining
        if batch:
            inserted, updated = upsert_tickets(
                bq_client,
                settings.gcp_project_id,
                batch,
            )
            total_inserted += inserted
            total_updated += updated

    # Save cursor for next run
    save_cursor(last_cursor, datetime.utcnow())

    logger.info(
        "Incremental ingestion complete",
        inserted=total_inserted,
        updated=total_updated,
    )


def main() -> None:
    """CLI entry point."""
    run_incremental()


if __name__ == "__main__":
    main()
