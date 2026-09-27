"""Application configuration via environment variables / .env file."""
import os
from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/.env, resolved independently of the process working directory
_BACKEND_ENV_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Later files take priority; real environment variables override both.
        env_file=(".env", _BACKEND_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Receipts API"
    app_version: str = "0.1.0"

    # Kept out of os.environ so subprocesses running PR code never inherit it.
    github_token: SecretStr = SecretStr("")

    # Comma-separated origins allowed in addition to localhost, e.g. the deployed frontend URL
    cors_origins: str = ""

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
