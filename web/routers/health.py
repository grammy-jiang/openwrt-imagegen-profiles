"""Health check endpoints."""

from fastapi import APIRouter

from openwrt_imagegen import __version__

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """Health check endpoint.

    Returns:
        Health status with version.
    """
    return {"status": "ok", "version": __version__}


@router.get("/")
def root() -> dict[str, str]:
    """Root endpoint.

    Returns:
        API name and version.
    """
    return {"name": "OpenWrt Image Generator API", "version": __version__}
