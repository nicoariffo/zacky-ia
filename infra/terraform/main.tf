terraform {
  required_version = ">= 1.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# BigQuery Datasets
resource "google_bigquery_dataset" "raw" {
  dataset_id    = "raw"
  friendly_name = "Raw Data"
  description   = "Raw tickets from Zendesk"
  location      = var.region

  labels = {
    environment = var.environment
    project     = "zacky-ia"
  }
}

resource "google_bigquery_dataset" "clean" {
  dataset_id    = "clean"
  friendly_name = "Clean Data"
  description   = "Processed and cleaned tickets"
  location      = var.region

  labels = {
    environment = var.environment
    project     = "zacky-ia"
  }
}

resource "google_bigquery_dataset" "features" {
  dataset_id    = "features"
  friendly_name = "Features"
  description   = "Embeddings, clusters, and intents"
  location      = var.region

  labels = {
    environment = var.environment
    project     = "zacky-ia"
  }
}

# BigQuery Tables - Raw
resource "google_bigquery_table" "raw_tickets" {
  dataset_id          = google_bigquery_dataset.raw.dataset_id
  table_id            = "tickets"
  deletion_protection = false

  schema = jsonencode([
    { name = "ticket_id", type = "INTEGER", mode = "REQUIRED" },
    { name = "subject", type = "STRING", mode = "NULLABLE" },
    { name = "description", type = "STRING", mode = "NULLABLE" },
    { name = "comments_json", type = "STRING", mode = "NULLABLE" },
    { name = "created_at", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "updated_at", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "tags", type = "STRING", mode = "REPEATED" },
    { name = "channel", type = "STRING", mode = "NULLABLE" },
    { name = "assignee_id", type = "INTEGER", mode = "NULLABLE" },
    { name = "status", type = "STRING", mode = "NULLABLE" },
    { name = "priority", type = "STRING", mode = "NULLABLE" },
    { name = "requester_email", type = "STRING", mode = "NULLABLE" },
    { name = "ingested_at", type = "TIMESTAMP", mode = "REQUIRED" }
  ])
}

# BigQuery Tables - Clean
resource "google_bigquery_table" "clean_tickets" {
  dataset_id          = google_bigquery_dataset.clean.dataset_id
  table_id            = "tickets"
  deletion_protection = false

  schema = jsonencode([
    { name = "ticket_id", type = "INTEGER", mode = "REQUIRED" },
    { name = "text_full", type = "STRING", mode = "NULLABLE" },
    { name = "text_customer_only", type = "STRING", mode = "NULLABLE" },
    { name = "text_agent_only", type = "STRING", mode = "NULLABLE" },
    { name = "channel", type = "STRING", mode = "NULLABLE" },
    { name = "word_count", type = "INTEGER", mode = "NULLABLE" },
    { name = "has_pii_redacted", type = "BOOLEAN", mode = "REQUIRED" },
    { name = "processed_at", type = "TIMESTAMP", mode = "REQUIRED" }
  ])
}

# BigQuery Tables - Features
resource "google_bigquery_table" "embeddings" {
  dataset_id          = google_bigquery_dataset.features.dataset_id
  table_id            = "embeddings"
  deletion_protection = false

  schema = jsonencode([
    { name = "ticket_id", type = "INTEGER", mode = "REQUIRED" },
    { name = "embedding_vector", type = "FLOAT64", mode = "REPEATED" },
    { name = "model_version", type = "STRING", mode = "REQUIRED" },
    { name = "created_at", type = "TIMESTAMP", mode = "REQUIRED" }
  ])
}

resource "google_bigquery_table" "clusters" {
  dataset_id          = google_bigquery_dataset.features.dataset_id
  table_id            = "clusters"
  deletion_protection = false

  schema = jsonencode([
    { name = "ticket_id", type = "INTEGER", mode = "REQUIRED" },
    { name = "cluster_id", type = "INTEGER", mode = "REQUIRED" },
    { name = "distance_to_centroid", type = "FLOAT64", mode = "NULLABLE" },
    { name = "is_noise", type = "BOOLEAN", mode = "REQUIRED" },
    { name = "umap_x", type = "FLOAT64", mode = "NULLABLE" },
    { name = "umap_y", type = "FLOAT64", mode = "NULLABLE" },
    { name = "created_at", type = "TIMESTAMP", mode = "REQUIRED" }
  ])
}

resource "google_bigquery_table" "intents" {
  dataset_id          = google_bigquery_dataset.features.dataset_id
  table_id            = "intents"
  deletion_protection = false

  schema = jsonencode([
    { name = "intent_id", type = "STRING", mode = "REQUIRED" },
    { name = "cluster_id", type = "INTEGER", mode = "REQUIRED" },
    { name = "name", type = "STRING", mode = "REQUIRED" },
    { name = "description", type = "STRING", mode = "NULLABLE" },
    { name = "volume", type = "INTEGER", mode = "REQUIRED" },
    { name = "avg_resolution_time_hours", type = "FLOAT64", mode = "NULLABLE" },
    { name = "repetition_score", type = "FLOAT64", mode = "NULLABLE" },
    { name = "risk_level", type = "STRING", mode = "NULLABLE" },
    { name = "composite_score", type = "FLOAT64", mode = "NULLABLE" },
    { name = "status", type = "STRING", mode = "REQUIRED" },
    { name = "created_at", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "updated_at", type = "TIMESTAMP", mode = "REQUIRED" }
  ])
}

resource "google_bigquery_table" "suggestions" {
  dataset_id          = google_bigquery_dataset.features.dataset_id
  table_id            = "suggestions"
  deletion_protection = false

  schema = jsonencode([
    { name = "suggestion_id", type = "STRING", mode = "REQUIRED" },
    { name = "ticket_id", type = "INTEGER", mode = "REQUIRED" },
    { name = "intent_id", type = "STRING", mode = "NULLABLE" },
    { name = "response_text", type = "STRING", mode = "REQUIRED" },
    { name = "confidence_score", type = "FLOAT64", mode = "REQUIRED" },
    { name = "similar_ticket_ids", type = "INTEGER", mode = "REPEATED" },
    { name = "prompt_version", type = "STRING", mode = "NULLABLE" },
    { name = "created_at", type = "TIMESTAMP", mode = "REQUIRED" }
  ])
}

resource "google_bigquery_table" "feedback" {
  dataset_id          = google_bigquery_dataset.features.dataset_id
  table_id            = "feedback"
  deletion_protection = false

  schema = jsonencode([
    { name = "feedback_id", type = "STRING", mode = "REQUIRED" },
    { name = "suggestion_id", type = "STRING", mode = "REQUIRED" },
    { name = "ticket_id", type = "INTEGER", mode = "REQUIRED" },
    { name = "agent_id", type = "STRING", mode = "NULLABLE" },
    { name = "action", type = "STRING", mode = "REQUIRED" },
    { name = "edited_text", type = "STRING", mode = "NULLABLE" },
    { name = "rejection_reason", type = "STRING", mode = "NULLABLE" },
    { name = "created_at", type = "TIMESTAMP", mode = "REQUIRED" }
  ])
}

# Cloud Storage bucket for artifacts
resource "google_storage_bucket" "artifacts" {
  name          = "${var.project_id}-zacky-artifacts"
  location      = var.region
  force_destroy = true

  uniform_bucket_level_access = true

  labels = {
    environment = var.environment
    project     = "zacky-ia"
  }
}

# Service Account for the application
resource "google_service_account" "zacky_app" {
  account_id   = "zacky-app"
  display_name = "Zacky IA Application"
  description  = "Service account for Zacky IA application"
}

# IAM bindings for the service account
resource "google_project_iam_member" "zacky_bigquery_admin" {
  project = var.project_id
  role    = "roles/bigquery.admin"
  member  = "serviceAccount:${google_service_account.zacky_app.email}"
}

resource "google_project_iam_member" "zacky_storage_admin" {
  project = var.project_id
  role    = "roles/storage.admin"
  member  = "serviceAccount:${google_service_account.zacky_app.email}"
}

# Outputs
output "raw_dataset_id" {
  value = google_bigquery_dataset.raw.dataset_id
}

output "clean_dataset_id" {
  value = google_bigquery_dataset.clean.dataset_id
}

output "features_dataset_id" {
  value = google_bigquery_dataset.features.dataset_id
}

output "artifacts_bucket" {
  value = google_storage_bucket.artifacts.name
}

output "service_account_email" {
  value = google_service_account.zacky_app.email
}
