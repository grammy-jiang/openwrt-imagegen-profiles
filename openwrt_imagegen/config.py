"""Configuration settings for openwrt_imagegen.

Uses pydantic-settings for config parsing from environment variables
and defaults. Configuration precedence: CLI flags > env vars > defaults.
"""

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_cache_dir() -> Path:
    """Return the default cache directory."""
    return Path.home() / ".cache" / "openwrt-imagegen" / "builders"


def _default_artifacts_dir() -> Path:
    """Return the default artifacts directory."""
    return Path.home() / ".local" / "share" / "openwrt-imagegen" / "artifacts"


def _default_db_url() -> str:
    """Return the default database URL (SQLite)."""
    db_path = Path.home() / ".local" / "share" / "openwrt-imagegen" / "db.sqlite"
    return f"sqlite:///{db_path}"


class Settings(BaseSettings):
    """Application settings.

    Settings are loaded from environment variables with the OWRT_IMG_ prefix.
    CLI flags can override these at runtime.
    """

    model_config = SettingsConfigDict(
        env_prefix="OWRT_IMG_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Paths
    cache_dir: Path = Field(
        default_factory=_default_cache_dir,
        description="Root directory for Image Builder cache",
    )
    artifacts_dir: Path = Field(
        default_factory=_default_artifacts_dir,
        description="Root directory for build artifacts",
    )
    db_url: str = Field(
        default_factory=_default_db_url,
        description="Database connection URL",
    )
    tmp_dir: Path | None = Field(
        default=None,
        description="Temporary directory for builds (uses system default if not set)",
    )

    # Operational modes
    offline: bool = Field(
        default=False,
        description="Offline mode - do not download Image Builders",
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Logging level",
    )

    # Concurrency
    max_concurrent_downloads: int = Field(
        default=2,
        ge=1,
        le=10,
        description="Maximum concurrent Image Builder downloads",
    )
    max_concurrent_builds: int = Field(
        default=2,
        ge=1,
        le=10,
        description="Maximum concurrent builds",
    )

    # Verification
    verification_mode: Literal["full-hash", "prefix-16MiB", "prefix-64MiB", "skip"] = (
        Field(
            default="full-hash",
            description="Default verification mode for flashing",
        )
    )

    # Timeouts (in seconds)
    download_timeout: int = Field(
        default=3600,
        ge=60,
        description="Timeout for Image Builder downloads",
    )
    build_timeout: int = Field(
        default=3600,
        ge=60,
        description="Timeout for builds",
    )
    flash_timeout: int = Field(
        default=1800,
        ge=60,
        description="Timeout for flash operations",
    )


def get_settings() -> Settings:
    """Get the application settings singleton.

    Returns:
        Settings instance loaded from environment.
    """
    return Settings()


def print_settings_json(settings: Settings | None = None) -> str:
    """Render effective settings as JSON.

    Args:
        settings: Optional settings instance; uses default if not provided.

    Returns:
        JSON string of effective settings.
    """
    if settings is None:
        settings = get_settings()
    return settings.model_dump_json(indent=2)


__all__ = ["Settings", "get_settings", "print_settings_json"]
