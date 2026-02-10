#!/usr/bin/env python3
"""Setup BigQuery datasets and tables programmatically (alternative to Terraform)."""

from google.cloud import bigquery

from src.config import get_settings


def create_datasets(client: bigquery.Client, project_id: str, location: str) -> None:
    """Create the required BigQuery datasets."""
    datasets = ["raw", "clean", "features"]

    for dataset_name in datasets:
        dataset_id = f"{project_id}.{dataset_name}"
        dataset = bigquery.Dataset(dataset_id)
        dataset.location = location

        dataset = client.create_dataset(dataset, exists_ok=True)
        print(f"Dataset {dataset.dataset_id} created/verified")


def create_raw_tickets_table(client: bigquery.Client, project_id: str) -> None:
    """Create raw_tickets table."""
    table_id = f"{project_id}.raw.tickets"

    schema = [
        bigquery.SchemaField("ticket_id", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("subject", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("description", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("comments_json", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("updated_at", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("tags", "STRING", mode="REPEATED"),
        bigquery.SchemaField("channel", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("assignee_id", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("status", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("priority", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("requester_email", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("ingested_at", "TIMESTAMP", mode="REQUIRED"),
    ]

    table = bigquery.Table(table_id, schema=schema)
    table = client.create_table(table, exists_ok=True)
    print(f"Table {table.table_id} created/verified")


def create_clean_tickets_table(client: bigquery.Client, project_id: str) -> None:
    """Create clean_tickets table."""
    table_id = f"{project_id}.clean.tickets"

    schema = [
        bigquery.SchemaField("ticket_id", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("text_full", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("text_customer_only", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("text_agent_only", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("channel", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("word_count", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("has_pii_redacted", "BOOLEAN", mode="REQUIRED"),
        bigquery.SchemaField("processed_at", "TIMESTAMP", mode="REQUIRED"),
    ]

    table = bigquery.Table(table_id, schema=schema)
    table = client.create_table(table, exists_ok=True)
    print(f"Table {table.table_id} created/verified")


def create_feature_tables(client: bigquery.Client, project_id: str) -> None:
    """Create feature tables (embeddings, clusters, intents, suggestions, feedback)."""
    # Embeddings
    embeddings_schema = [
        bigquery.SchemaField("ticket_id", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("embedding_vector", "FLOAT64", mode="REPEATED"),
        bigquery.SchemaField("model_version", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
    ]
    table = bigquery.Table(f"{project_id}.features.embeddings", schema=embeddings_schema)
    client.create_table(table, exists_ok=True)
    print("Table embeddings created/verified")

    # Clusters
    clusters_schema = [
        bigquery.SchemaField("ticket_id", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("cluster_id", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("distance_to_centroid", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("is_noise", "BOOLEAN", mode="REQUIRED"),
        bigquery.SchemaField("umap_x", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("umap_y", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
    ]
    table = bigquery.Table(f"{project_id}.features.clusters", schema=clusters_schema)
    client.create_table(table, exists_ok=True)
    print("Table clusters created/verified")

    # Intents
    intents_schema = [
        bigquery.SchemaField("intent_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("cluster_id", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("name", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("description", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("volume", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("avg_resolution_time_hours", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("repetition_score", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("risk_level", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("composite_score", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("status", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("updated_at", "TIMESTAMP", mode="REQUIRED"),
    ]
    table = bigquery.Table(f"{project_id}.features.intents", schema=intents_schema)
    client.create_table(table, exists_ok=True)
    print("Table intents created/verified")

    # Suggestions
    suggestions_schema = [
        bigquery.SchemaField("suggestion_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("ticket_id", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("intent_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("response_text", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("confidence_score", "FLOAT64", mode="REQUIRED"),
        bigquery.SchemaField("similar_ticket_ids", "INTEGER", mode="REPEATED"),
        bigquery.SchemaField("prompt_version", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
    ]
    table = bigquery.Table(f"{project_id}.features.suggestions", schema=suggestions_schema)
    client.create_table(table, exists_ok=True)
    print("Table suggestions created/verified")

    # Feedback
    feedback_schema = [
        bigquery.SchemaField("feedback_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("suggestion_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("ticket_id", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("agent_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("action", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("edited_text", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("rejection_reason", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
    ]
    table = bigquery.Table(f"{project_id}.features.feedback", schema=feedback_schema)
    client.create_table(table, exists_ok=True)
    print("Table feedback created/verified")


def main() -> None:
    settings = get_settings()
    client = bigquery.Client(project=settings.gcp_project_id)

    print(f"Setting up BigQuery for project: {settings.gcp_project_id}")

    create_datasets(client, settings.gcp_project_id, settings.gcp_location)
    create_raw_tickets_table(client, settings.gcp_project_id)
    create_clean_tickets_table(client, settings.gcp_project_id)
    create_feature_tables(client, settings.gcp_project_id)

    print("\nBigQuery setup complete!")


if __name__ == "__main__":
    main()
