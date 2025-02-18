from __future__ import annotations

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

from src import consts


class OAuthSettings(BaseModel):
    client_id: str
    client_secret: str


class SentinelHubSettings(OAuthSettings):
    stac_api_endpoint: str = "https://creodias.sentinel-hub.com/api/v1/catalog/1.0.0/"
    process_api_endpoint: str = "https://creodias.sentinel-hub.com/api/v1/process"
    token_endpoint: str = "https://services.sentinel-hub.com/auth/realms/main/protocol/openid-connect/token"


class EODHSettings(BaseSettings):
    stac_api_endpoint: str = "https://staging.eodatahub.org.uk/api/catalogue/stac"


class Settings(BaseSettings):
    """Represents Application Settings with nested configuration sections."""

    environment: str = "local"
    sentinel_hub: SentinelHubSettings
    eodh: EODHSettings

    model_config = SettingsConfigDict(
        env_file=consts.directories.ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )


def current_settings() -> Settings:
    return Settings()
