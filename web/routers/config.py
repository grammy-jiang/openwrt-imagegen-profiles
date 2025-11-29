"""Configuration endpoints."""

from typing import Any

from fastapi import APIRouter

from openwrt_imagegen.config import get_settings

router = APIRouter()


@router.get("")
def get_config() -> dict[str, Any]:
    """Get effective configuration.

    Returns:
        Current configuration as JSON.
    """
    settings = get_settings()
    return {
        "cache_dir": str(settings.cache_dir),
        "artifacts_dir": str(settings.artifacts_dir),
        "db_url": settings.db_url,
        "tmp_dir": str(settings.tmp_dir) if settings.tmp_dir else None,
        "offline": settings.offline,
        "log_level": settings.log_level,
        "verification_mode": settings.verification_mode,
        "max_concurrent_downloads": settings.max_concurrent_downloads,
        "max_concurrent_builds": settings.max_concurrent_builds,
        "download_timeout": settings.download_timeout,
        "build_timeout": settings.build_timeout,
        "flash_timeout": settings.flash_timeout,
    }
