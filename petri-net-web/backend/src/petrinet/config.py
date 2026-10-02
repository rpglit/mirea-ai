"""Application settings from environment variables (NFR-004)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration; every field has a default, so no `.env` is needed.

    Field names map to environment variables case-insensitively:
    LOG_LEVEL, DB_PATH, REACH_MAX_MARKINGS, PETRINET_STATIC_DIR.

    Example:
        settings = get_settings()
        assert settings.log_level in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    log_level: str = "INFO"

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        """Normalize to upper case and reject unknown levels."""
        normalized = value.upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"unknown log level: {value!r}")
        return normalized
    db_path: str = "/data/sessions.db"
    reach_max_markings: int = 50000
    petrinet_static_dir: str = "/app/static"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide Settings instance, built once and cached.

    Example:
        settings = get_settings()
        print(settings.db_path, settings.reach_max_markings)
    """
    return Settings()
