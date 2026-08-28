from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration shared by CLI commands and workers."""

    model_config = SettingsConfigDict(
        env_prefix="TRACY_",
        env_file=".env",
        extra="ignore",
    )

    environment: str = "development"
    log_level: str = "INFO"
    data_dir: Path = Path("data")
    database_url: str = "postgresql+asyncpg://tracy:tracy@localhost:5432/tracy"
    moodle_base_url: str | None = None
    moodle_token: str | None = None
    moodle_profile_dir: Path = Path("data/browser-profile")
    moodle_headless: bool = False
    timezone: str = "Asia/Kolkata"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "gemma3:4b"


def get_settings() -> Settings:
    return Settings()
