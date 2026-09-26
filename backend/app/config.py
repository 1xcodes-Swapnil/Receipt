"""Application configuration via environment variables / .env file."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # silently ignore unknown .env keys
    )

    app_name: str = "Receipts API"
    app_version: str = "0.1.0"

    # SQLite by default; swap for postgresql+psycopg2://... for PostgreSQL
    database_url: str = "sqlite:///./database/receipts.db"
    db_echo: bool = False

    # Absolute or relative path to the demo repository
    demo_repo_path: str = "./demo/repository"

    # GitHub integration
    github_token: str = ""

    # Application
    debug: bool = False
    max_parallel_agents: int = 4

    # Replay engine
    replay_max_cases: int = 0

    # Advanced strategies (Phase 6)
    strategy_max_iterations: int = 50
    strategy_seed: int = 0          # 0 = per-run deterministic seed
    strategy_timeout_seconds: int = 30

    # Immunity pipeline (Phase 7)
    immunity_max_fix_retries: int = 3

    # Audit
    audit_log_stdout: bool = False


settings = Settings()
