"""Application configuration loaded from environment variables."""
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings from .env file."""

    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/interactive_course"

    # LLM
    llm_model: str = "ollama/llama3"
    llm_api_base: str | None = "http://localhost:11434"
    llm_api_key: str | None = None
    llm_timeout_seconds: int = 120
    llm_max_retries: int = 3

    # Uploads
    upload_dir: str = "./uploads"

    # Logging
    log_level: str = "INFO"
    log_file: str = "logs/app.log"
    log_max_bytes: int = 10_000_000  # 10MB
    log_backup_count: int = 5

    # App
    app_name: str = "Interactive Course Platform"
    app_version: str = "0.2.0"
    debug: bool = False

    # CORS
    cors_origins: str = "*"  # Comma-separated origins or * for all

    @property
    def videos_dir(self) -> Path:
        path = Path(self.upload_dir) / "videos"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def assets_dir(self) -> Path:
        path = Path(self.upload_dir) / "assets"
        path.mkdir(parents=True, exist_ok=True)
        return path

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


settings = Settings()
