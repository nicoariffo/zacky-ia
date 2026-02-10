"""Clustering tickets using UMAP + HDBSCAN."""

import time
from typing import Any

import hdbscan
import numpy as np
import structlog
import umap
from google.cloud import bigquery
from sklearn.metrics import silhouette_score

from src.config import get_settings

logger = structlog.get_logger()

# UMAP parameters for dimensionality reduction
UMAP_N_NEIGHBORS = 15
UMAP_MIN_DIST = 0.1
UMAP_N_COMPONENTS = 25  # Reduce to 25 dims for clustering
UMAP_N_COMPONENTS_VIZ = 2  # For visualization

# HDBSCAN parameters
HDBSCAN_MIN_CLUSTER_SIZE_PCT = 0.03  # 3% of dataset
HDBSCAN_MIN_SAMPLES = 5


def load_embeddings(
    bq_client: bigquery.Client,
    project_id: str,
    limit: int | None = None,
) -> tuple[list[int], np.ndarray]:
    """
    Load embeddings from BigQuery.

    Returns:
        Tuple of (ticket_ids, embeddings_array)
    """
    embeddings_table = f"{project_id}.features.embeddings"

    query = f"""
        SELECT ticket_id, embedding_vector
        FROM `{embeddings_table}`
        ORDER BY ticket_id
    """

    if limit:
        query += f" LIMIT {limit}"

    logger.info("Loading embeddings from BigQuery")
    results = list(bq_client.query(query).result())

    ticket_ids = [row["ticket_id"] for row in results]
    embeddings = np.array([row["embedding_vector"] for row in results])

    logger.info("Loaded embeddings", count=len(ticket_ids), shape=embeddings.shape)
    return ticket_ids, embeddings


def reduce_dimensions(
    embeddings: np.ndarray,
    n_components: int = UMAP_N_COMPONENTS,
) -> np.ndarray:
    """
    Reduce embedding dimensions using UMAP.

    Args:
        embeddings: High-dimensional embeddings (N, 1536)
        n_components: Target dimensions

    Returns:
        Reduced embeddings (N, n_components)
    """
    logger.info(
        "Reducing dimensions with UMAP",
        from_dims=embeddings.shape[1],
        to_dims=n_components,
    )

    reducer = umap.UMAP(
        n_neighbors=UMAP_N_NEIGHBORS,
        min_dist=UMAP_MIN_DIST,
        n_components=n_components,
        metric="cosine",
        random_state=42,
    )

    reduced = reducer.fit_transform(embeddings)
    logger.info("UMAP complete", output_shape=reduced.shape)

    return reduced


def cluster_embeddings(
    embeddings: np.ndarray,
    min_cluster_size: int | None = None,
) -> tuple[np.ndarray, hdbscan.HDBSCAN]:
    """
    Cluster embeddings using HDBSCAN.

    Args:
        embeddings: Reduced embeddings
        min_cluster_size: Minimum cluster size (defaults to 3% of dataset)

    Returns:
        Tuple of (labels, clusterer)
    """
    if min_cluster_size is None:
        min_cluster_size = max(20, int(len(embeddings) * HDBSCAN_MIN_CLUSTER_SIZE_PCT))

    logger.info(
        "Clustering with HDBSCAN",
        n_samples=len(embeddings),
        min_cluster_size=min_cluster_size,
        min_samples=HDBSCAN_MIN_SAMPLES,
    )

    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=HDBSCAN_MIN_SAMPLES,
        metric="euclidean",
        cluster_selection_method="eom",
    )

    labels = clusterer.fit_predict(embeddings)

    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = (labels == -1).sum()
    noise_pct = n_noise / len(labels) * 100

    logger.info(
        "Clustering complete",
        n_clusters=n_clusters,
        n_noise=n_noise,
        noise_pct=round(noise_pct, 1),
    )

    return labels, clusterer


def calculate_metrics(
    embeddings: np.ndarray,
    labels: np.ndarray,
) -> dict[str, float]:
    """Calculate clustering quality metrics."""
    # Only calculate silhouette on non-noise points
    mask = labels != -1
    if mask.sum() < 2:
        return {"silhouette_score": 0.0, "noise_ratio": 1.0}

    silhouette = silhouette_score(embeddings[mask], labels[mask])
    noise_ratio = (~mask).sum() / len(labels)

    return {
        "silhouette_score": round(silhouette, 4),
        "noise_ratio": round(noise_ratio, 4),
    }


def run_clustering(
    limit: int | None = None,
    min_cluster_size: int | None = None,
) -> dict[str, Any]:
    """
    Run the full clustering pipeline.

    Args:
        limit: Optional limit on number of embeddings to process
        min_cluster_size: Optional override for min cluster size

    Returns:
        Dict with clustering statistics
    """
    settings = get_settings()
    bq_client = bigquery.Client(project=settings.gcp_project_id)

    # Load embeddings
    ticket_ids, embeddings = load_embeddings(
        bq_client, settings.gcp_project_id, limit
    )

    if len(ticket_ids) == 0:
        logger.warning("No embeddings found")
        return {"error": "No embeddings found"}

    # Reduce dimensions for clustering
    embeddings_reduced = reduce_dimensions(embeddings, UMAP_N_COMPONENTS)

    # Reduce dimensions for visualization
    embeddings_viz = reduce_dimensions(embeddings, UMAP_N_COMPONENTS_VIZ)

    # Cluster
    labels, clusterer = cluster_embeddings(embeddings_reduced, min_cluster_size)

    # Calculate metrics
    metrics = calculate_metrics(embeddings_reduced, labels)

    # Calculate distance to centroid for each point
    # For noise points, use distance to nearest cluster centroid
    distances = np.zeros(len(labels))
    for cluster_id in set(labels):
        if cluster_id == -1:
            continue
        mask = labels == cluster_id
        cluster_points = embeddings_reduced[mask]
        centroid = cluster_points.mean(axis=0)
        distances[mask] = np.linalg.norm(cluster_points - centroid, axis=1)

    # For noise points, calculate distance to nearest cluster
    noise_mask = labels == -1
    if noise_mask.any():
        cluster_centroids = []
        for cluster_id in set(labels):
            if cluster_id == -1:
                continue
            mask = labels == cluster_id
            centroid = embeddings_reduced[mask].mean(axis=0)
            cluster_centroids.append(centroid)

        if cluster_centroids:
            centroids_array = np.array(cluster_centroids)
            noise_points = embeddings_reduced[noise_mask]
            noise_distances = np.min(
                np.linalg.norm(
                    noise_points[:, np.newaxis] - centroids_array, axis=2
                ),
                axis=1,
            )
            distances[noise_mask] = noise_distances

    # Prepare data for BigQuery
    clusters_table = f"{settings.gcp_project_id}.features.clusters"

    rows = [
        {
            "ticket_id": int(ticket_id),
            "cluster_id": int(label),
            "distance_to_centroid": float(dist),
            "is_noise": bool(label == -1),
            "umap_x": float(embeddings_viz[i, 0]),
            "umap_y": float(embeddings_viz[i, 1]),
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        for i, (ticket_id, label, dist) in enumerate(
            zip(ticket_ids, labels, distances)
        )
    ]

    # Insert in batches
    batch_size = 500
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        insert_errors = bq_client.insert_rows_json(clusters_table, batch)
        if insert_errors:
            logger.error("BigQuery insert errors", errors=insert_errors[:3])

    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)

    stats = {
        "total_tickets": len(ticket_ids),
        "n_clusters": n_clusters,
        "noise_count": int((labels == -1).sum()),
        **metrics,
    }

    logger.info("Clustering pipeline complete", **stats)
    return stats


def main() -> None:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Cluster ticket embeddings")
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of embeddings to process",
    )
    parser.add_argument(
        "--min-cluster-size",
        type=int,
        help="Minimum cluster size for HDBSCAN",
    )

    args = parser.parse_args()

    stats = run_clustering(
        limit=args.limit,
        min_cluster_size=args.min_cluster_size,
    )

    print("\n=== Clustering Complete ===")
    print(f"Total tickets: {stats.get('total_tickets', 0)}")
    print(f"Clusters found: {stats.get('n_clusters', 0)}")
    print(f"Noise points: {stats.get('noise_count', 0)}")
    print(f"Silhouette score: {stats.get('silhouette_score', 0):.4f}")


if __name__ == "__main__":
    main()
