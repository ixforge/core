"""Application settings via Pydantic Settings."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModuleFlags(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="IXFORGE_MODULE_")

    ui: bool = False
    switching: bool = False
    rpki: bool = False
    peeringdb_sync: bool = False
    ixf_export: bool = True


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="IXFORGE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Core
    debug: bool = False
    secret_key: str = "change-me-to-a-random-string-at-least-32-chars"

    # Database
    database_url: str = "postgresql+asyncpg://ixforge:ixforge@localhost:5432/ixforge"

    # CORS
    cors_origins: list[str] = Field(default=["*"])

    # Rate limiting
    rate_limit_per_minute: int = 60

    # Modules
    modules: ModuleFlags = Field(default_factory=ModuleFlags)


@lru_cache
def get_settings() -> Settings:
    return Settings()
