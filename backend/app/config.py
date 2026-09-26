"""Application configuration via environment variables / .env file."""
import os
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Receipts API"
    app_version: str = "0.1.0"

    # SQLite by default; swap for postgresql+psycopg2://... for PostgreSQL
    database_url: str = "sqlite:///./database/receipts.db"
    db_echo: bool = False

    # Absolute or relative path to the demo repository
    demo_repo_path: str = "./demo/repository"

    @field_validator("demo_repo_path", mode="after")
    @classmethod
    def resolve_demo_repo_path(cls, v: str) -> str:
        if v and os.path.exists(v) and os.path.isdir(v):
            return os.path.abspath(v)

        candidates = [
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "demo", "repository")),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "demo", "repository")),
            os.path.abspath("./demo/repository"),
            os.path.abspath("../demo/repository"),
        ]
        for candidate in candidates:
            if os.path.exists(candidate) and os.path.isdir(candidate):
                return os.path.abspath(candidate)

        return os.path.abspath(v or "./demo/repository")


settings = Settings()
