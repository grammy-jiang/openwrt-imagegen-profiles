"""Image Builder management endpoints.

Per docs/FRONTENDS.md:
- GET /builders - List Image Builders
- GET /builders/{release}/{target}/{subtarget} - Get specific builder
- POST /builders/ensure - Ensure a builder is available
- POST /builders/prune - Prune unused builders
- GET /builders/info - Cache information
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from openwrt_imagegen.config import get_settings
from openwrt_imagegen.imagebuilder.service import (
    ImageBuilderBrokenError,
    ImageBuilderNotFoundError,
    OfflineModeError,
    ensure_builder,
    get_builder,
    get_builder_cache_info,
    list_builders,
    prune_builders,
)
from openwrt_imagegen.types import ImageBuilderState
from web.deps import get_db

router = APIRouter()


class EnsureBuilderRequest(BaseModel):
    """Request body for ensuring a builder is available."""

    release: str
    target: str
    subtarget: str
    force_download: bool = False


class PruneRequest(BaseModel):
    """Request body for pruning builders."""

    deprecated_only: bool = True
    dry_run: bool = False


def _builder_to_dict(builder: Any) -> dict[str, Any]:
    """Convert a builder ORM instance to a dictionary."""
    return {
        "openwrt_release": builder.openwrt_release,
        "target": builder.target,
        "subtarget": builder.subtarget,
        "state": builder.state,
        "root_dir": builder.root_dir,
        "checksum": builder.checksum,
        "signature_verified": builder.signature_verified,
        "first_used_at": builder.first_used_at.isoformat()
        if builder.first_used_at
        else None,
        "last_used_at": builder.last_used_at.isoformat()
        if builder.last_used_at
        else None,
    }


@router.get("")
def list_builders_endpoint(
    release: str | None = Query(None, description="Filter by release"),
    target: str | None = Query(None, description="Filter by target"),
    subtarget: str | None = Query(None, description="Filter by subtarget"),
    state: str | None = Query(None, description="Filter by state"),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """List cached Image Builders.

    Args:
        release: Filter by release.
        target: Filter by target.
        subtarget: Filter by subtarget.
        state: Filter by state.
        db: Database session.

    Returns:
        List of Image Builders.
    """
    state_filter: ImageBuilderState | None = None
    if state:
        try:
            state_filter = ImageBuilderState(state)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "invalid_state",
                    "message": f"Invalid state: {state}. Valid values: pending, ready, broken, deprecated",
                },
            ) from None

    builders = list_builders(
        db,
        release=release,
        target=target,
        subtarget=subtarget,
        state=state_filter,
    )
    return [_builder_to_dict(b) for b in builders]


@router.get("/info")
def get_cache_info_endpoint() -> dict[str, Any]:
    """Get Image Builder cache information.

    Returns:
        Cache information.
    """
    info = get_builder_cache_info()
    return dict(info)


@router.get("/{release}/{target}/{subtarget}")
def get_builder_endpoint(
    release: str,
    target: str,
    subtarget: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Get a specific Image Builder.

    Args:
        release: OpenWrt release.
        target: Target platform.
        subtarget: Subtarget.
        db: Database session.

    Returns:
        Image Builder data.

    Raises:
        HTTPException: If builder not found.
    """
    try:
        builder = get_builder(db, release, target, subtarget)
        return _builder_to_dict(builder)
    except ImageBuilderNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "imagebuilder_not_found",
                "message": f"Image Builder not found: {release}/{target}/{subtarget}",
            },
        ) from None


@router.post("/ensure")
def ensure_builder_endpoint(
    request: EnsureBuilderRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Ensure an Image Builder is available.

    Downloads the builder if not cached.

    Args:
        request: Ensure request parameters.
        db: Database session.

    Returns:
        Image Builder data.

    Raises:
        HTTPException: If download fails or offline mode.
    """
    settings = get_settings()

    try:
        builder = ensure_builder(
            db,
            release=request.release,
            target=request.target,
            subtarget=request.subtarget,
            settings=settings,
            force_download=request.force_download,
        )
        return _builder_to_dict(builder)
    except OfflineModeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "offline_mode",
                "message": "Cannot download in offline mode",
            },
        ) from None
    except ImageBuilderBrokenError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "imagebuilder_broken",
                "message": f"Image Builder is broken: {request.release}/{request.target}/{request.subtarget}. Use force_download=true to re-download.",
            },
        ) from None
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "ensure_failed",
                "message": str(e),
            },
        ) from e


@router.post("/prune")
def prune_builders_endpoint(
    request: PruneRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Prune unused or deprecated Image Builders.

    Args:
        request: Prune request parameters.
        db: Database session.

    Returns:
        Prune results.
    """
    settings = get_settings()

    pruned = prune_builders(
        db,
        deprecated_only=request.deprecated_only,
        settings=settings,
        dry_run=request.dry_run,
    )

    return {
        "dry_run": request.dry_run,
        "pruned_count": len(pruned),
        "pruned": [{"release": r, "target": t, "subtarget": s} for r, t, s in pruned],
    }
