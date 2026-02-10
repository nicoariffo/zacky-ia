"""Generate embeddings for tickets using OpenAI API."""

import time
from typing import Any

import structlog
from google.cloud import bigquery
from openai import OpenAI

from src.config import get_settings

logger = structlog.get_logger()

BATCH_SIZE = 100  # OpenAI recommends batches of 100
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536


def get_openai_client() -> OpenAI:
    """Get OpenAI client."""
    settings = get_settings()
    return OpenAI(api_key=settings.openai_api_key)


def generate_embeddings_batch(
    client: OpenAI,
    texts: list[str],
) -> list[list[float]]:
    """
    Generate embeddings for a batch of texts.

    Args:
        client: OpenAI client
        texts: List of texts to embed

    Returns:
        List of embedding vectors
    """
    # Replace empty texts with a placeholder
    texts = [t if t and t.strip() else "[vacío]" for t in texts]

    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts,
    )

    # Sort by index to maintain order
    embeddings = sorted(response.data, key=lambda x: x.index)
    return [e.embedding for e in embeddings]


def run_embeddings(
    limit: int | None = None,
    reprocess: bool = False,
) -> dict[str, Any]:
    """
    Generate embeddings for all clean tickets.

    Args:
        limit: Optional limit on number of tickets to process
        reprocess: Whether to reprocess already processed tickets

    Returns:
        Dict with processing statistics
    """
    settings = get_settings()
    bq_client = bigquery.Client(project=settings.gcp_project_id)
    openai_client = get_openai_client()

    clean_table = f"{settings.gcp_project_id}.clean.tickets"
    embeddings_table = f"{settings.gcp_project_id}.features.embeddings"

    # Build query to get tickets needing embeddings
    if reprocess:
        query = f"""
            SELECT ticket_id, text_customer_only
            FROM `{clean_table}`
            WHERE text_customer_only IS NOT NULL
        """
    else:
        query = f"""
            SELECT c.ticket_id, c.text_customer_only
            FROM `{clean_table}` c
            LEFT JOIN `{embeddings_table}` e ON c.ticket_id = e.ticket_id
            WHERE e.ticket_id IS NULL
            AND c.text_customer_only IS NOT NULL
        """

    if limit:
        query += f" LIMIT {limit}"

    logger.info("Fetching tickets for embedding", query=query[:100])

    results = list(bq_client.query(query).result())
    total_tickets = len(results)

    if total_tickets == 0:
        logger.info("No tickets to process")
        return {"processed": 0, "errors": 0}

    logger.info("Starting embedding generation", total_tickets=total_tickets)

    processed = 0
    errors = 0

    # Process in batches
    for i in range(0, total_tickets, BATCH_SIZE):
        batch = results[i : i + BATCH_SIZE]
        ticket_ids = [row["ticket_id"] for row in batch]
        texts = [row["text_customer_only"] or "" for row in batch]

        try:
            embeddings = generate_embeddings_batch(openai_client, texts)

            # Prepare rows for BigQuery
            rows = [
                {
                    "ticket_id": ticket_id,
                    "embedding_vector": embedding,
                    "model_version": EMBEDDING_MODEL,
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
                for ticket_id, embedding in zip(ticket_ids, embeddings)
            ]

            # Insert to BigQuery
            insert_errors = bq_client.insert_rows_json(embeddings_table, rows)
            if insert_errors:
                logger.error("BigQuery insert errors", errors=insert_errors[:3])
                errors += len(insert_errors)
            else:
                processed += len(batch)

            logger.info(
                "Progress",
                processed=processed,
                total=total_tickets,
                pct=round(processed / total_tickets * 100, 1),
            )

            # Rate limiting - be nice to OpenAI
            time.sleep(0.5)

        except Exception as e:
            logger.error("Error processing batch", error=str(e), batch_start=i)
            errors += len(batch)

    stats = {
        "processed": processed,
        "errors": errors,
        "total_tickets": total_tickets,
    }

    logger.info("Embedding generation complete", **stats)
    return stats


def main() -> None:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Generate embeddings for tickets")
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

    args = parser.parse_args()

    stats = run_embeddings(limit=args.limit, reprocess=args.reprocess)
    print("\n=== Embedding Generation Complete ===")
    print(f"Processed: {stats['processed']}")
    print(f"Errors: {stats['errors']}")


if __name__ == "__main__":
    main()
