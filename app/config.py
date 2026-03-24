"""Application configuration loaded from environment variables."""
import os
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

    # Uploads
    upload_dir: str = "./uploads"

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
