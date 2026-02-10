from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Zendesk
    zendesk_subdomain: str
    zendesk_email: str
    zendesk_api_token: str

    # OpenAI
    openai_api_key: str

    # Google Cloud
    gcp_project_id: str
    gcp_location: str = "us-central1"
    bigquery_dataset_raw: str = "raw"
    bigquery_dataset_clean: str = "clean"
    bigquery_dataset_features: str = "features"

    # API
    api_key: str
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Environment
    environment: str = "development"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def get_bq_table(self, dataset: str, table: str) -> str:
        return f"{self.gcp_project_id}.{dataset}.{table}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
