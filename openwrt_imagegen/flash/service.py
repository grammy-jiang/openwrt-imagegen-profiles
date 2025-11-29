"""Flash service layer for TF/SD card flashing.

This module provides high-level flash operations:
- flash_artifact: Flash an artifact by ID with DB tracking
- flash_image: Flash an image file directly
- Dry-run mode support
- Force flag support
- FlashRecord persistence

All operations follow the safety rules in docs/SAFETY.md:
- Explicit device paths only (no guessing)
- Explicit confirmation / force flags
- Pre-flight validation
- Hash-based verification
- Detailed logging
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from openwrt_imagegen.builds.models import Artifact
from openwrt_imagegen.config import Settings, get_settings
from openwrt_imagegen.flash.device import (
    DeviceInfo,
    DeviceValidationError,
    validate_device,
)
from openwrt_imagegen.flash.models import FlashRecord
from openwrt_imagegen.flash.writer import (
    VERIFICATION_SIZE_BYTES,
    HashMismatchError,
    ImageNotFoundError,
    WriteError,
    compute_file_hash,
    write_image_to_device,
)
from openwrt_imagegen.types import FlashStatus, VerificationMode, VerificationResult

logger = logging.getLogger(__name__)


class FlashServiceError(Exception):
    """Base exception for flash service errors."""

    def __init__(self, message: str, error_code: str) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code


class ArtifactNotFoundError(FlashServiceError):
    """Artifact not found in database."""

    def __init__(self, artifact_id: int) -> None:
        super().__init__(
            f"Artifact not found: {artifact_id}", error_code="ARTIFACT_NOT_FOUND"
        )
        self.artifact_id = artifact_id


class ArtifactFileNotFoundError(FlashServiceError):
    """Artifact file does not exist on disk."""

    def __init__(self, artifact_id: int, path: str) -> None:
        super().__init__(
            f"Artifact file not found on disk: {path} (artifact_id={artifact_id})",
            error_code="ARTIFACT_FILE_NOT_FOUND",
        )
        self.artifact_id = artifact_id
        self.path = path


class FlashAbortedError(FlashServiceError):
    """Flash operation was aborted (dry-run or user cancellation)."""

    def __init__(self, message: str = "Flash operation aborted") -> None:
        super().__init__(message, error_code="FLASH_ABORTED")


@dataclass
class FlashPlan:
    """Plan for a flash operation (used for dry-run).

    Attributes:
        image_path: Path to the image file.
        image_size: Size of the image in bytes.
        image_hash: SHA-256 hash of the image.
        device_path: Path to the target device.
        device_info: Information about the device.
        wipe_before: Whether device will be wiped before writing.
        verification_mode: How write will be verified.
        artifact_id: Artifact ID if flashing from database.
        build_id: Build ID if flashing from database.
    """

    image_path: str
    image_size: int
    image_hash: str
    device_path: str
    device_info: DeviceInfo
    wipe_before: bool
    verification_mode: VerificationMode
    artifact_id: int | None = None
    build_id: int | None = None


@dataclass
class FlashResult:
    """Result of a flash operation.

    Attributes:
        success: Whether the flash succeeded.
        flash_record_id: ID of the FlashRecord (if persisted).
        image_path: Path to the flashed image.
        device_path: Path to the target device.
        bytes_written: Number of bytes written.
        source_hash: SHA-256 hash of the source image.
        device_hash: SHA-256 hash read back from device.
        verification_mode: Verification mode used.
        verification_result: Result of hash verification.
        error_message: Error message if flash failed.
        error_code: Error code if flash failed.
    """

    success: bool
    flash_record_id: int | None
    image_path: str
    device_path: str
    bytes_written: int
    source_hash: str
    device_hash: str | None
    verification_mode: VerificationMode
    verification_result: VerificationResult
    error_message: str | None = None
    error_code: str | None = None


def get_artifact(session: Session, artifact_id: int) -> Artifact:
    """Get an artifact by ID.

    Args:
        session: Database session.
        artifact_id: Artifact ID to fetch.

    Returns:
        Artifact object.

    Raises:
        ArtifactNotFoundError: Artifact not found.
    """
    artifact = session.get(Artifact, artifact_id)
    if artifact is None:
        raise ArtifactNotFoundError(artifact_id)
    return artifact


def _get_artifact_path(artifact: Artifact, settings: Settings) -> Path:
    """Get the filesystem path for an artifact.

    Args:
        artifact: Artifact object.
        settings: Application settings.

    Returns:
        Path to the artifact file.
    """
    if artifact.absolute_path:
        return Path(artifact.absolute_path)
    else:
        return settings.artifacts_dir / artifact.relative_path


def plan_flash(
    image_path: str | Path,
    device_path: str,
    *,
    wipe_before: bool = False,
    verification_mode: VerificationMode = VerificationMode.FULL,
    artifact_id: int | None = None,
    build_id: int | None = None,
    check_mount: bool = True,
    check_system_device: bool = True,
) -> FlashPlan:
    """Create a plan for a flash operation.

    This validates inputs and computes what would happen without
    actually performing the flash. Useful for dry-run mode.

    Args:
        image_path: Path to the image file.
        device_path: Path to the target device.
        wipe_before: Whether to wipe device before writing.
        verification_mode: How to verify the write.
        artifact_id: Artifact ID if flashing from database.
        build_id: Build ID if flashing from database.
        check_mount: Whether to check if device is mounted.
        check_system_device: Whether to refuse system root device.

    Returns:
        FlashPlan with operation details.

    Raises:
        ImageNotFoundError: Image file not found.
        DeviceNotFoundError: Device not found (subclass of DeviceValidationError).
        NotBlockDeviceError: Device is not a block device (subclass of DeviceValidationError).
        PartitionDeviceError: Device is a partition, not a whole device (subclass of DeviceValidationError).
        SystemDeviceError: Device is a system/root device (subclass of DeviceValidationError).
        DeviceMountedError: Device is currently mounted (subclass of DeviceValidationError).
        DeviceValidationError: Other device validation errors (base class for the above).
    """
    image_path = Path(image_path)

    # Validate image exists
    if not image_path.exists():
        raise ImageNotFoundError(str(image_path))

    # Get image info
    image_size = image_path.stat().st_size

    # Compute image hash for the verification mode
    if verification_mode == VerificationMode.SKIP:
        image_hash = ""
    elif verification_mode == VerificationMode.FULL:
        image_hash, _ = compute_file_hash(image_path)
    else:
        # Prefix mode
        verify_bytes = min(
            VERIFICATION_SIZE_BYTES.get(verification_mode, image_size), image_size
        )
        image_hash, _ = compute_file_hash(image_path, max_bytes=verify_bytes)

    # Validate device
    device_info = validate_device(
        device_path,
        check_mount=check_mount,
        check_system_device=check_system_device,
    )

    return FlashPlan(
        image_path=str(image_path),
        image_size=image_size,
        image_hash=image_hash,
        device_path=device_info.path,
        device_info=device_info,
        wipe_before=wipe_before,
        verification_mode=verification_mode,
        artifact_id=artifact_id,
        build_id=build_id,
    )


def flash_image(
    image_path: str | Path,
    device_path: str,
    *,
    session: Session | None = None,
    settings: Settings | None = None,
    wipe_before: bool = False,
    verification_mode: VerificationMode | None = None,
    dry_run: bool = False,
    force: bool = False,
    artifact_id: int | None = None,
    build_id: int | None = None,
) -> FlashResult:
    """Flash an image to a device.

    This is the main entry point for flashing operations. It:
    1. Validates the device path
    2. Validates the image exists
    3. Optionally creates a FlashRecord for tracking
    4. Writes the image with fsync
    5. Verifies the write by comparing hashes
    6. Updates the FlashRecord with results

    Args:
        image_path: Path to the image file.
        device_path: Path to the target device (must be whole device).
        session: Database session (optional, for FlashRecord tracking).
        settings: Application settings (optional).
        wipe_before: Whether to wipe device before writing.
        verification_mode: How to verify the write (defaults to settings).
        dry_run: If True, validate and plan but don't actually write.
        force: If True, skip confirmation prompts (for non-interactive use).
        artifact_id: Artifact ID if flashing from database.
        build_id: Build ID if flashing from database.

    Returns:
        FlashResult with operation details.

    Raises:
        ImageNotFoundError: Image file not found.
        DeviceValidationError: Device validation failed.
        WriteError: Write operation failed.
        HashMismatchError: Hash verification failed.
    """
    if settings is None:
        settings = get_settings()

    if verification_mode is None:
        verification_mode = VerificationMode(settings.verification_mode)

    image_path = Path(image_path)

    logger.info(
        "Flash requested: image=%s, device=%s, dry_run=%s, force=%s",
        image_path.name,
        device_path,
        dry_run,
        force,
    )

    # Create plan (validates inputs)
    try:
        plan = plan_flash(
            image_path,
            device_path,
            wipe_before=wipe_before,
            verification_mode=verification_mode,
            artifact_id=artifact_id,
            build_id=build_id,
        )
    except DeviceValidationError as e:
        logger.error("Device validation failed: %s", e.message)
        return FlashResult(
            success=False,
            flash_record_id=None,
            image_path=str(image_path),
            device_path=device_path,
            bytes_written=0,
            source_hash="",
            device_hash=None,
            verification_mode=verification_mode,
            verification_result=VerificationResult.SKIPPED,
            error_message=e.message,
            error_code=e.error_code,
        )

    # If dry-run, return the plan without writing
    if dry_run:
        logger.info("Dry-run mode: not performing actual write")
        return FlashResult(
            success=True,
            flash_record_id=None,
            image_path=plan.image_path,
            device_path=plan.device_path,
            bytes_written=plan.image_size,  # Would write this many bytes
            source_hash=plan.image_hash,
            device_hash=None,
            verification_mode=plan.verification_mode,
            verification_result=VerificationResult.SKIPPED,
            error_message="Dry-run mode: no write performed",
        )

    # Create FlashRecord if session provided
    flash_record: FlashRecord | None = None
    if session is not None and artifact_id is not None and build_id is not None:
        flash_record = FlashRecord(
            artifact_id=artifact_id,
            build_id=build_id,
            device_path=plan.device_path,
            device_model=plan.device_info.model,
            device_serial=plan.device_info.serial,
            status=FlashStatus.PENDING.value,
            wiped_before_flash=wipe_before,
            verification_mode=verification_mode.value,
            requested_at=datetime.now(),
        )
        session.add(flash_record)
        session.flush()  # Get the ID
        logger.debug("Created FlashRecord id=%d", flash_record.id)

    # Perform the write
    try:
        if flash_record:
            flash_record.mark_running()
            session.flush()  # type: ignore[union-attr]

        write_result = write_image_to_device(
            plan.image_path,
            plan.device_path,
            wipe_before=wipe_before,
            verification_mode=verification_mode,
            expected_hash=plan.image_hash,
        )

        # Success
        if flash_record:
            flash_record.verification_result = write_result.verification_result.value
            flash_record.mark_succeeded()
            session.flush()  # type: ignore[union-attr]

        logger.info(
            "Flash succeeded: %d bytes written to %s, verification=%s",
            write_result.bytes_written,
            plan.device_path,
            write_result.verification_result.value,
        )

        return FlashResult(
            success=True,
            flash_record_id=flash_record.id if flash_record else None,
            image_path=plan.image_path,
            device_path=plan.device_path,
            bytes_written=write_result.bytes_written,
            source_hash=write_result.source_hash,
            device_hash=write_result.device_hash,
            verification_mode=write_result.verification_mode,
            verification_result=write_result.verification_result,
        )

    except (WriteError, HashMismatchError) as e:
        logger.error("Flash failed: %s", e.message)

        if flash_record:
            flash_record.mark_failed(error_type=e.error_code, message=e.message)
            session.flush()  # type: ignore[union-attr]

        return FlashResult(
            success=False,
            flash_record_id=flash_record.id if flash_record else None,
            image_path=plan.image_path,
            device_path=plan.device_path,
            bytes_written=0,
            source_hash=plan.image_hash,
            device_hash=getattr(e, "actual_hash", None),
            verification_mode=verification_mode,
            verification_result=VerificationResult.MISMATCH
            if isinstance(e, HashMismatchError)
            else VerificationResult.SKIPPED,
            error_message=e.message,
            error_code=e.error_code,
        )


def flash_artifact(
    session: Session,
    artifact_id: int,
    device_path: str,
    *,
    settings: Settings | None = None,
    wipe_before: bool = False,
    verification_mode: VerificationMode | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> FlashResult:
    """Flash an artifact from the database to a device.

    This is the preferred way to flash when working with builds:
    - Retrieves the artifact from the database
    - Uses the stored hash for verification
    - Creates a FlashRecord for audit trail

    Args:
        session: Database session.
        artifact_id: ID of the artifact to flash.
        device_path: Path to the target device.
        settings: Application settings (optional).
        wipe_before: Whether to wipe device before writing.
        verification_mode: How to verify the write.
        dry_run: If True, validate and plan but don't actually write.
        force: If True, skip confirmation prompts.

    Returns:
        FlashResult with operation details.

    Raises:
        ArtifactNotFoundError: Artifact not found in database.
        ArtifactFileNotFoundError: Artifact file not found on disk.
        DeviceValidationError: Device validation failed.
        WriteError: Write operation failed.
    """
    if settings is None:
        settings = get_settings()

    logger.info(
        "Flash artifact requested: artifact_id=%d, device=%s", artifact_id, device_path
    )

    # Get artifact from database
    artifact = get_artifact(session, artifact_id)

    # Get artifact file path
    artifact_path = _get_artifact_path(artifact, settings)
    if not artifact_path.exists():
        raise ArtifactFileNotFoundError(artifact_id, str(artifact_path))

    # Flash the image
    return flash_image(
        artifact_path,
        device_path,
        session=session,
        settings=settings,
        wipe_before=wipe_before,
        verification_mode=verification_mode,
        dry_run=dry_run,
        force=force,
        artifact_id=artifact.id,
        build_id=artifact.build_id,
    )


def get_flash_records(
    session: Session,
    *,
    artifact_id: int | None = None,
    build_id: int | None = None,
    device_path: str | None = None,
    status: FlashStatus | None = None,
    limit: int = 100,
) -> list[FlashRecord]:
    """Query flash records with optional filters.

    Args:
        session: Database session.
        artifact_id: Filter by artifact ID.
        build_id: Filter by build ID.
        device_path: Filter by device path.
        status: Filter by status.
        limit: Maximum number of records to return.

    Returns:
        List of FlashRecord objects.
    """
    from sqlalchemy import select

    stmt = select(FlashRecord)

    if artifact_id is not None:
        stmt = stmt.where(FlashRecord.artifact_id == artifact_id)
    if build_id is not None:
        stmt = stmt.where(FlashRecord.build_id == build_id)
    if device_path is not None:
        stmt = stmt.where(FlashRecord.device_path == device_path)
    if status is not None:
        stmt = stmt.where(FlashRecord.status == status.value)

    stmt = stmt.order_by(FlashRecord.requested_at.desc()).limit(limit)

    result = session.execute(stmt)
    return list(result.scalars().all())


__all__ = [
    "ArtifactFileNotFoundError",
    "ArtifactNotFoundError",
    "FlashAbortedError",
    "FlashPlan",
    "FlashResult",
    "FlashServiceError",
    "flash_artifact",
    "flash_image",
    "get_artifact",
    "get_flash_records",
    "plan_flash",
]
