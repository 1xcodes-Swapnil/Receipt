"""Application configuration via environment variables / .env file."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    app_name: str = "Receipts API"
    app_version: str = "0.1.0"

    # SQLite by default; swap for postgresql+psycopg2://... for PostgreSQL
    database_url: str = "sqlite:///./database/receipts.db"
    db_echo: bool = False

    # Absolute or relative path to the demo repository
    demo_repo_path: str = "./demo/repository"


settings = Settings()
