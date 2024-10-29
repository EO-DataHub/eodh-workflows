from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

from src import consts


class Settings(BaseSettings):
    """Represents Application Settings with nested configuration sections."""

    environment: str = "local"
    sh_client_id: str
    sh_secret: str

    model_config = SettingsConfigDict(
        env_file=consts.directories.ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )


def current_settings() -> Settings:
    return Settings()
