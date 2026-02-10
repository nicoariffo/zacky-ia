#!/usr/bin/env python3
"""Processing pipeline for cleaning and transforming tickets."""

from datetime import datetime
from typing import Any

import structlog
from google.cloud import bigquery

from src.config import get_settings
from src.processing.cleaner import TextCleaner
from src.processing.pii_redactor import PIIRedactor

logger = structlog.get_logger()


BATCH_SIZE = 100


def process_and_store_ticket(
    cleaner: TextCleaner,
    redactor: PIIRedactor,
    raw_ticket: dict[str, Any],
) -> dict[str, Any]:
    """
    Process a single raw ticket through cleaning and PII redaction.

    Args:
        cleaner: TextCleaner instance
        redactor: PIIRedactor instance
        raw_ticket: Raw ticket data from BigQuery

    Returns:
        Dict ready for BigQuery insertion
    """
    # Clean the ticket
    cleaned = cleaner.process_ticket(
        ticket_id=raw_ticket["ticket_id"],
        subject=raw_ticket.get("subject"),
        description=raw_ticket.get("description"),
        comments_json=raw_ticket.get("comments_json"),
        channel=raw_ticket.get("channel"),
        requester_email=raw_ticket.get("requester_email"),
    )

    # Redact PII from all text fields
    full_result = redactor.redact(cleaned.text_full)
    customer_result = redactor.redact(cleaned.text_customer_only)
    agent_result = redactor.redact(cleaned.text_agent_only)

    has_pii = full_result.has_pii or customer_result.has_pii or agent_result.has_pii

    return {
        "ticket_id": cleaned.ticket_id,
        "text_full": full_result.text,
        "text_customer_only": customer_result.text,
        "text_agent_only": agent_result.text,
        "channel": cleaned.channel,
        "word_count": cleaned.word_count,
        "has_pii_redacted": has_pii,
        "processed_at": datetime.utcnow().isoformat(),
    }


def run_pipeline(
    limit: int | None = None,
    reprocess: bool = False,
) -> dict[str, int]:
    """
    Run the full processing pipeline.

    Args:
        limit: Maximum number of tickets to process (None = all)
        reprocess: Whether to reprocess already processed tickets

    Returns:
        Dict with processing statistics
    """
    settings = get_settings()
    bq_client = bigquery.Client(project=settings.gcp_project_id)

    raw_table = f"{settings.gcp_project_id}.raw.tickets"
    clean_table = f"{settings.gcp_project_id}.clean.tickets"

    # Build query to get unprocessed tickets
    if reprocess:
        query = f"SELECT * FROM `{raw_table}`"
    else:
        query = f"""
            SELECT r.*
            FROM `{raw_table}` r
            LEFT JOIN `{clean_table}` c ON r.ticket_id = c.ticket_id
            WHERE c.ticket_id IS NULL
        """

    if limit:
        query += f" LIMIT {limit}"

    logger.info("Fetching raw tickets", query=query[:100])

    # Initialize processors
    cleaner = TextCleaner()
    redactor = PIIRedactor()

    # Process in batches
    processed = 0
    pii_found = 0
    errors = 0

    results = bq_client.query(query).result()

    batch: list[dict[str, Any]] = []

    for row in results:
        try:
            raw_ticket = dict(row)
            processed_ticket = process_and_store_ticket(cleaner, redactor, raw_ticket)
            batch.append(processed_ticket)

            if processed_ticket["has_pii_redacted"]:
                pii_found += 1

            if len(batch) >= BATCH_SIZE:
                # Insert batch
                insert_errors = bq_client.insert_rows_json(clean_table, batch)
                if insert_errors:
                    logger.error("Insert errors", errors=insert_errors[:3])
                    errors += len(insert_errors)
                processed += len(batch)
                logger.info("Progress", processed=processed, pii_found=pii_found)
                batch = []

        except Exception as e:
            logger.error(
                "Error processing ticket",
                ticket_id=row.get("ticket_id"),
                error=str(e),
            )
            errors += 1

    # Insert remaining batch
    if batch:
        insert_errors = bq_client.insert_rows_json(clean_table, batch)
        if insert_errors:
            errors += len(insert_errors)
        processed += len(batch)

    stats = {
        "processed": processed,
        "pii_found": pii_found,
        "errors": errors,
        "pii_rate": pii_found / processed if processed > 0 else 0,
    }

    logger.info("Pipeline complete", **stats)

    return stats


def generate_qa_report(sample_size: int = 100) -> dict[str, Any]:
    """
    Generate a QA report on the cleaning and PII redaction quality.

    Args:
        sample_size: Number of tickets to sample for QA

    Returns:
        QA report with statistics and sample issues
    """
    settings = get_settings()
    bq_client = bigquery.Client(project=settings.gcp_project_id)

    clean_table = f"{settings.gcp_project_id}.clean.tickets"

    # Get sample of cleaned tickets
    query = f"""
        SELECT *
        FROM `{clean_table}`
        ORDER BY RAND()
        LIMIT {sample_size}
    """

    results = bq_client.query(query).result()

    redactor = PIIRedactor()

    # Check for remaining PII in cleaned text
    remaining_pii: list[dict[str, Any]] = []
    total_checked = 0
    with_remaining_pii = 0

    for row in results:
        total_checked += 1
        ticket_id = row["ticket_id"]

        # Check all text fields
        for field in ["text_full", "text_customer_only", "text_agent_only"]:
            text = row.get(field, "")
            if text:
                remaining = redactor.validate_redaction(text)
                if remaining:
                    with_remaining_pii += 1
                    remaining_pii.append({
                        "ticket_id": ticket_id,
                        "field": field,
                        "remaining_pii": remaining,
                    })

    report = {
        "sample_size": total_checked,
        "tickets_with_remaining_pii": with_remaining_pii,
        "false_negative_rate": with_remaining_pii / total_checked if total_checked > 0 else 0,
        "sample_issues": remaining_pii[:10],  # First 10 issues
    }

    logger.info("QA Report generated", **{k: v for k, v in report.items() if k != "sample_issues"})

    return report


def main() -> None:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Run ticket processing pipeline")
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of tickets to process",
    )
    parser.add_argument(
        "--reprocess",
        action="store_true",
        help="Reprocess all tickets (including already processed)",
    )
    parser.add_argument(
        "--qa-report",
        action="store_true",
        help="Generate QA report instead of processing",
    )
    parser.add_argument(
        "--qa-sample",
        type=int,
        default=100,
        help="Sample size for QA report",
    )

    args = parser.parse_args()

    if args.qa_report:
        report = generate_qa_report(args.qa_sample)
        print("\n=== QA Report ===")
        print(f"Sample size: {report['sample_size']}")
        print(f"Tickets with remaining PII: {report['tickets_with_remaining_pii']}")
        print(f"False negative rate: {report['false_negative_rate']:.2%}")
        if report["sample_issues"]:
            print("\nSample issues:")
            for issue in report["sample_issues"][:5]:
                print(f"  Ticket {issue['ticket_id']}: {issue['remaining_pii']}")
    else:
        stats = run_pipeline(limit=args.limit, reprocess=args.reprocess)
        print("\n=== Processing Complete ===")
        print(f"Processed: {stats['processed']}")
        print(f"PII found: {stats['pii_found']} ({stats['pii_rate']:.2%})")
        print(f"Errors: {stats['errors']}")


if __name__ == "__main__":
    main()
