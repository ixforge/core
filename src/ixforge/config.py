"""Application settings via Pydantic Settings."""

from functools import lru_cache

from pydantic import Field, model_validator
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
    cors_origins: list[str] = Field(default_factory=list)

    # Rate limiting
    rate_limit_per_minute: int = 60

    # Media
    media_root: str = "./media"
    media_url: str = "/media"

    # UI
    core_url: str = "http://localhost:8000"
    ui_port: int = 8001

    # Modules
    modules: ModuleFlags = Field(default_factory=ModuleFlags)

    @model_validator(mode="after")
    def _validate_settings(self) -> "Settings":
        default = "change-me-to-a-random-string-at-least-32-chars"
        if not self.debug and self.secret_key == default:
            raise ValueError(
                "IXFORGE_SECRET_KEY must be set to a secure random value in production"
            )
        if not self.debug and len(self.secret_key) < 32:
            raise ValueError("IXFORGE_SECRET_KEY must be at least 32 characters")
        if self.debug and self.secret_key == default:
            import warnings

            warnings.warn(
                "Using default SECRET_KEY in debug mode. "
                "This is insecure and must not be used in production",
                UserWarning,
                stacklevel=2,
            )
        if self.debug and not self.cors_origins:
            self.cors_origins = [
                "http://localhost:3000",
                "http://localhost:8001",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:8001",
            ]
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
