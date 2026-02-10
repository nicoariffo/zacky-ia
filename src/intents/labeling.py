"""Auto-labeling of clusters using LLM."""

import json
from typing import Any

import structlog
from google.cloud import bigquery
from openai import OpenAI

from src.config import get_settings

logger = structlog.get_logger()

LABELING_MODEL = "gpt-4o-mini"
TOP_EXAMPLES_PER_CLUSTER = 5


def get_cluster_examples(
    bq_client: bigquery.Client,
    project_id: str,
    cluster_id: int,
    n_examples: int = TOP_EXAMPLES_PER_CLUSTER,
) -> list[dict[str, Any]]:
    """
    Get representative examples from a cluster (closest to centroid).

    Args:
        bq_client: BigQuery client
        project_id: GCP project ID
        cluster_id: Cluster to get examples from
        n_examples: Number of examples to return

    Returns:
        List of ticket examples with text
    """
    query = f"""
        SELECT
            c.ticket_id,
            c.distance_to_centroid,
            t.text_customer_only,
            t.text_full
        FROM `{project_id}.features.clusters` c
        JOIN `{project_id}.clean.tickets` t ON c.ticket_id = t.ticket_id
        WHERE c.cluster_id = {cluster_id}
        ORDER BY c.distance_to_centroid ASC
        LIMIT {n_examples}
    """

    results = list(bq_client.query(query).result())
    return [dict(row) for row in results]


def generate_cluster_label(
    openai_client: OpenAI,
    examples: list[dict[str, Any]],
) -> dict[str, str]:
    """
    Generate a label and description for a cluster using LLM.

    Args:
        openai_client: OpenAI client
        examples: Representative examples from the cluster

    Returns:
        Dict with 'name' and 'description' keys
    """
    # Build examples text
    examples_text = "\n\n".join(
        f"Ejemplo {i+1}:\n{ex['text_customer_only'][:500]}"
        for i, ex in enumerate(examples)
    )

    prompt = f"""Analiza los siguientes tickets de soporte al cliente de una tienda de retail/e-commerce.

Estos tickets pertenecen al mismo grupo temático. Tu tarea es:
1. Identificar el tema principal o "intent" que los une
2. Proponer un nombre corto (máximo 4 palabras) en español
3. Escribir una descripción breve (1-2 oraciones) del tipo de consulta

TICKETS:
{examples_text}

Responde SOLO en formato JSON con esta estructura exacta:
{{
    "name": "nombre del intent",
    "description": "descripción breve del tipo de consulta"
}}"""

    response = openai_client.chat.completions.create(
        model=LABELING_MODEL,
        messages=[
            {
                "role": "system",
                "content": "Eres un experto en clasificación de tickets de soporte. Responde solo en JSON válido.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=200,
    )

    # Parse JSON response
    content = response.choices[0].message.content.strip()

    # Clean markdown if present
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
        content = content.strip()

    try:
        result = json.loads(content)
        return {
            "name": result.get("name", "Sin clasificar"),
            "description": result.get("description", ""),
        }
    except json.JSONDecodeError:
        logger.warning("Failed to parse LLM response", content=content[:100])
        return {"name": "Sin clasificar", "description": content[:200]}


def get_cluster_stats(
    bq_client: bigquery.Client,
    project_id: str,
) -> list[dict[str, Any]]:
    """Get statistics for all clusters."""
    query = f"""
        SELECT
            cluster_id,
            COUNT(*) as volume,
            AVG(distance_to_centroid) as avg_distance,
            MIN(distance_to_centroid) as min_distance,
            MAX(distance_to_centroid) as max_distance
        FROM `{project_id}.features.clusters`
        WHERE cluster_id >= 0
        GROUP BY cluster_id
        ORDER BY volume DESC
    """

    results = list(bq_client.query(query).result())
    return [dict(row) for row in results]


def run_labeling(
    limit_clusters: int | None = None,
) -> dict[str, Any]:
    """
    Generate labels for all clusters.

    Args:
        limit_clusters: Optional limit on number of clusters to label

    Returns:
        Dict with labeling statistics
    """
    settings = get_settings()
    bq_client = bigquery.Client(project=settings.gcp_project_id)
    openai_client = OpenAI(api_key=settings.openai_api_key)

    # Get cluster stats
    cluster_stats = get_cluster_stats(bq_client, settings.gcp_project_id)

    if limit_clusters:
        cluster_stats = cluster_stats[:limit_clusters]

    logger.info("Starting cluster labeling", n_clusters=len(cluster_stats))

    intents_table = f"{settings.gcp_project_id}.features.intents"
    labeled = 0
    errors = 0

    for stats in cluster_stats:
        cluster_id = stats["cluster_id"]

        try:
            # Get examples
            examples = get_cluster_examples(
                bq_client, settings.gcp_project_id, cluster_id
            )

            if not examples:
                continue

            # Generate label
            label = generate_cluster_label(openai_client, examples)

            # Prepare row for BigQuery
            import time

            now = time.strftime("%Y-%m-%d %H:%M:%S")
            row = {
                "intent_id": str(cluster_id),
                "cluster_id": cluster_id,
                "name": label["name"],
                "description": label["description"],
                "volume": stats["volume"],
                "status": "pending",  # Requires human validation
                "created_at": now,
                "updated_at": now,
            }

            # Insert to BigQuery
            insert_errors = bq_client.insert_rows_json(intents_table, [row])
            if insert_errors:
                logger.error(
                    "BigQuery insert error",
                    cluster_id=cluster_id,
                    errors=insert_errors,
                )
                errors += 1
            else:
                labeled += 1
                logger.info(
                    "Labeled cluster",
                    cluster_id=cluster_id,
                    name=label["name"],
                    volume=stats["volume"],
                )

        except Exception as e:
            logger.error("Error labeling cluster", cluster_id=cluster_id, error=str(e))
            errors += 1

    result = {
        "total_clusters": len(cluster_stats),
        "labeled": labeled,
        "errors": errors,
    }

    logger.info("Labeling complete", **result)
    return result


def get_intent_summary(
    limit: int = 20,
) -> list[dict[str, Any]]:
    """
    Get summary of labeled intents.

    Args:
        limit: Maximum number of intents to return

    Returns:
        List of intent summaries
    """
    settings = get_settings()
    bq_client = bigquery.Client(project=settings.gcp_project_id)

    query = f"""
        SELECT
            intent_id,
            name,
            description,
            volume,
            status
        FROM `{settings.gcp_project_id}.features.intents`
        ORDER BY volume DESC
        LIMIT {limit}
    """

    results = list(bq_client.query(query).result())
    return [dict(row) for row in results]


def main() -> None:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Generate labels for clusters")
    parser.add_argument(
        "--limit-clusters",
        type=int,
        help="Maximum number of clusters to label",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Show summary of existing intents",
    )

    args = parser.parse_args()

    if args.summary:
        intents = get_intent_summary()
        print("\n=== Intent Summary ===")
        for intent in intents:
            print(f"\n[{intent['intent_id']}] {intent['name']}")
            print(f"    Volume: {intent['volume']} tickets")
            print(f"    {intent['description']}")
    else:
        stats = run_labeling(limit_clusters=args.limit_clusters)
        print("\n=== Labeling Complete ===")
        print(f"Total clusters: {stats['total_clusters']}")
        print(f"Labeled: {stats['labeled']}")
        print(f"Errors: {stats['errors']}")


if __name__ == "__main__":
    main()
