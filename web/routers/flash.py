"""Flash operation endpoints.

Per docs/FRONTENDS.md and docs/SAFETY.md:
- POST /flash - Flash an artifact to a device
- GET /flash - List flash records

All operations require explicit device paths and follow safety rules.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from openwrt_imagegen.config import get_settings
from openwrt_imagegen.flash.service import (
    ArtifactFileNotFoundError,
    ArtifactNotFoundError,
    flash_artifact,
    get_flash_records,
)
from openwrt_imagegen.types import FlashStatus
from web.deps import get_db

router = APIRouter()


class FlashRequest(BaseModel):
    """Request body for flash operation."""

    artifact_id: int
    device_path: str
    wipe_before: bool = False
    dry_run: bool = False
    force: bool = False


def _flash_record_to_dict(record: Any) -> dict[str, Any]:
    """Convert a flash record to a dictionary."""
    return {
        "id": record.id,
        "artifact_id": record.artifact_id,
        "build_id": record.build_id,
        "device_path": record.device_path,
        "device_model": record.device_model,
        "device_serial": record.device_serial,
        "status": record.status,
        "wiped_before_flash": record.wiped_before_flash,
        "verification_mode": record.verification_mode,
        "verification_result": record.verification_result,
        "requested_at": record.requested_at.isoformat()
        if record.requested_at
        else None,
        "started_at": record.started_at.isoformat() if record.started_at else None,
        "finished_at": record.finished_at.isoformat() if record.finished_at else None,
        "error_type": record.error_type,
        "error_message": record.error_message,
        "log_path": record.log_path,
    }


@router.get("")
def list_flash_records_endpoint(
    artifact_id: int | None = Query(None, description="Filter by artifact ID"),
    build_id: int | None = Query(None, description="Filter by build ID"),
    device: str | None = Query(None, description="Filter by device path"),
    status: str | None = Query(None, description="Filter by status"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """List flash records.

    Args:
        artifact_id: Filter by artifact ID.
        build_id: Filter by build ID.
        device: Filter by device path.
        status: Filter by status.
        limit: Maximum results.
        db: Database session.

    Returns:
        List of flash records.
    """
    status_filter: FlashStatus | None = None
    if status:
        try:
            status_filter = FlashStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "invalid_status",
                    "message": f"Invalid status: {status}. Valid values: pending, running, succeeded, failed",
                },
            ) from None

    records = get_flash_records(
        db,
        artifact_id=artifact_id,
        build_id=build_id,
        device_path=device,
        status=status_filter,
        limit=limit,
    )
    return [_flash_record_to_dict(r) for r in records]


@router.post("")
def flash_artifact_endpoint(
    request: FlashRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Flash an artifact to a device.

    Per docs/SAFETY.md:
    - Requires explicit device path (e.g., /dev/sdb, /dev/mmcblk0)
    - Never operates on partitions
    - Use dry_run=true to validate without writing
    - Use force=true to skip confirmation

    Args:
        request: Flash request parameters.
        db: Database session.

    Returns:
        Flash result.

    Raises:
        HTTPException: If artifact not found or validation fails.
    """
    settings = get_settings()

    try:
        result = flash_artifact(
            db,
            artifact_id=request.artifact_id,
            device_path=request.device_path,
            settings=settings,
            wipe_before=request.wipe_before,
            dry_run=request.dry_run,
            force=request.force,
        )

        if not request.dry_run:
            db.commit()

        return {
            "success": result.success,
            "flash_record_id": result.flash_record_id,
            "image_path": result.image_path,
            "device_path": result.device_path,
            "bytes_written": result.bytes_written,
            "source_hash": result.source_hash,
            "device_hash": result.device_hash,
            "verification_mode": result.verification_mode.value,
            "verification_result": result.verification_result.value,
            "message": result.message,
            "error_message": result.error_message,
            "error_code": result.error_code,
        }

    except ArtifactNotFoundError as e:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail={
                "code": "artifact_not_found",
                "message": f"Artifact not found: {e.artifact_id}",
            },
        ) from None
    except ArtifactFileNotFoundError as e:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail={
                "code": "artifact_file_not_found",
                "message": f"Artifact file not found: {e.path}",
            },
        ) from None
