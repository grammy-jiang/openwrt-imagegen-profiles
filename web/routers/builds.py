"""Build management endpoints.

Per docs/FRONTENDS.md section 3.2:
- GET /builds - List builds
- GET /builds/{id} - Get build by ID
- GET /builds/{id}/artifacts - Get artifacts for a build
- POST /builds - Start a build
- POST /builds/batch - Start batch builds
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from openwrt_imagegen.builds.models import Artifact
from openwrt_imagegen.builds.service import (
    BatchBuildFilter,
    BuildNotFoundError,
    build_batch,
    get_build,
    get_build_artifacts,
    list_builds,
)
from openwrt_imagegen.config import get_settings
from openwrt_imagegen.profiles.service import (
    ProfileNotFoundError,
    get_profile,
)
from openwrt_imagegen.types import BatchMode, BuildStatus
from web.deps import get_db

router = APIRouter()


class BatchBuildRequest(BaseModel):
    """Request body for batch builds."""

    profile_ids: list[str] | None = None
    device_id: str | None = None
    release: str | None = None
    target: str | None = None
    subtarget: str | None = None
    tags: list[str] | None = None
    mode: str = "best-effort"
    force_rebuild: bool = False


def _build_to_dict(build: Any) -> dict[str, Any]:
    """Convert a build record to a dictionary."""
    return {
        "id": build.id,
        "profile_id": build.profile.profile_id if build.profile else None,
        "status": build.status,
        "cache_key": build.cache_key,
        "is_cache_hit": build.is_cache_hit,
        "requested_at": build.requested_at.isoformat() if build.requested_at else None,
        "started_at": build.started_at.isoformat() if build.started_at else None,
        "finished_at": build.finished_at.isoformat() if build.finished_at else None,
        "log_path": build.log_path,
        "error_type": build.error_type,
        "error_message": build.error_message,
        "artifact_count": len(build.artifacts),
    }


def _artifact_to_dict(artifact: Artifact) -> dict[str, Any]:
    """Convert an artifact to a dictionary."""
    return {
        "id": artifact.id,
        "build_id": artifact.build_id,
        "kind": artifact.kind,
        "filename": artifact.filename,
        "relative_path": artifact.relative_path,
        "absolute_path": artifact.absolute_path,
        "size_bytes": artifact.size_bytes,
        "sha256": artifact.sha256,
        "labels": artifact.labels,
    }


@router.get("")
def list_builds_endpoint(
    profile: str | None = Query(None, description="Filter by profile ID"),
    status: str | None = Query(None, description="Filter by status"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """List build records.

    Args:
        profile: Filter by profile ID.
        status: Filter by status.
        limit: Maximum results.
        db: Database session.

    Returns:
        List of build records.
    """
    # Parse status filter
    status_filter: BuildStatus | None = None
    if status:
        try:
            status_filter = BuildStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "invalid_status",
                    "message": f"Invalid status: {status}. Valid values: pending, running, succeeded, failed",
                },
            ) from None

    # Resolve profile_id to database ID
    db_profile_id: int | None = None
    if profile:
        try:
            profile_obj = get_profile(db, profile)
            db_profile_id = profile_obj.id
        except ProfileNotFoundError:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "profile_not_found",
                    "message": f"Profile not found: {profile}",
                },
            ) from None

    builds = list_builds(
        db, profile_id=db_profile_id, status=status_filter, limit=limit
    )
    return [_build_to_dict(b) for b in builds]


@router.get("/{build_id}")
def get_build_endpoint(
    build_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Get a build record by ID.

    Args:
        build_id: Build ID.
        db: Database session.

    Returns:
        Build record data.

    Raises:
        HTTPException: If build not found.
    """
    try:
        build = get_build(db, build_id)
        return _build_to_dict(build)
    except BuildNotFoundError:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail={
                "code": "build_not_found",
                "message": f"Build not found: {build_id}",
            },
        ) from None


@router.get("/{build_id}/artifacts")
def get_build_artifacts_endpoint(
    build_id: int,
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Get artifacts for a build.

    Args:
        build_id: Build ID.
        db: Database session.

    Returns:
        List of artifacts.

    Raises:
        HTTPException: If build not found.
    """
    try:
        artifacts = get_build_artifacts(db, build_id)
        return [_artifact_to_dict(a) for a in artifacts]
    except BuildNotFoundError:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail={
                "code": "build_not_found",
                "message": f"Build not found: {build_id}",
            },
        ) from None


@router.post("/batch")
def batch_build_endpoint(
    request: BatchBuildRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Start batch builds for multiple profiles.

    Args:
        request: Batch build parameters.
        db: Database session.

    Returns:
        Batch build results.
    """
    # Validate at least one filter
    if not any(
        [
            request.profile_ids,
            request.device_id,
            request.release,
            request.target,
            request.subtarget,
            request.tags,
        ]
    ):
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "no_filter",
                "message": "At least one filter must be specified",
            },
        )

    # Validate mode
    try:
        batch_mode = BatchMode(request.mode)
    except ValueError:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "invalid_mode",
                "message": f"Invalid mode: {request.mode}. Valid values: fail-fast, best-effort",
            },
        ) from None

    settings = get_settings()

    filter_spec = BatchBuildFilter(
        profile_ids=request.profile_ids,
        device_id=request.device_id,
        openwrt_release=request.release,
        target=request.target,
        subtarget=request.subtarget,
        tags=request.tags,
    )

    result = build_batch(
        session=db,
        filter_spec=filter_spec,
        settings=settings,
        mode=batch_mode,
        force_rebuild=request.force_rebuild,
    )
    return result.model_dump()
