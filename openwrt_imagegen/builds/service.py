"""Build service module.

This module provides the high-level build API:
- build_or_reuse(): Main entry point - build with cache awareness
- Cache lookup by key
- Locking to prevent duplicate builds
- Build record and artifact persistence

See docs/BUILD_PIPELINE.md for design details.
"""

from __future__ import annotations

import fcntl
import logging
import os
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from openwrt_imagegen.builds.artifacts import (
    discover_artifacts,
    generate_manifest,
    write_manifest,
)
from openwrt_imagegen.builds.cache_key import compute_cache_key_from_profile
from openwrt_imagegen.builds.models import Artifact, BuildRecord
from openwrt_imagegen.builds.overlay import (
    OverlayStagingError,
    has_overlay_content,
    stage_and_hash_overlay,
)
from openwrt_imagegen.builds.runner import (
    BuildExecutionError,
    run_build,
    validate_imagebuilder_root,
)
from openwrt_imagegen.config import get_settings
from openwrt_imagegen.types import ArtifactInfo, BuildStatus

if TYPE_CHECKING:
    from openwrt_imagegen.config import Settings
    from openwrt_imagegen.imagebuilder.models import ImageBuilder
    from openwrt_imagegen.profiles.models import Profile
    from openwrt_imagegen.profiles.schema import ProfileSchema

logger = logging.getLogger(__name__)


class BuildNotFoundError(Exception):
    """Raised when a build is not found."""

    def __init__(self, build_id: int, code: str = "build_not_found") -> None:
        super().__init__(f"Build not found: {build_id}")
        self.build_id = build_id
        self.code = code


class CacheConflictError(Exception):
    """Raised when cache key conflict detected."""

    def __init__(self, cache_key: str, code: str = "cache_conflict") -> None:
        super().__init__(f"Cache conflict for key: {cache_key}")
        self.cache_key = cache_key
        self.code = code


class BuildServiceError(Exception):
    """Base error for build service operations."""

    def __init__(self, message: str, code: str = "build_service_error") -> None:
        super().__init__(message)
        self.code = code


@contextmanager
def build_lock(
    lock_dir: Path,
    cache_key: str,
    timeout: float | None = None,
) -> Iterator[None]:
    """Acquire a lock for a build cache key.

    Uses a file-based lock to prevent concurrent builds with the same key.

    Args:
        lock_dir: Directory for lock files.
        cache_key: Cache key to lock on.
        timeout: Lock acquisition timeout in seconds (None = blocking).

    Yields:
        None when lock is acquired.

    Raises:
        TimeoutError: If lock cannot be acquired within timeout.
    """
    lock_dir.mkdir(parents=True, exist_ok=True)

    # Create safe filename from cache key
    safe_key = cache_key.replace(":", "_").replace("/", "_")[:64]
    lock_file = lock_dir / f"build_{safe_key}.lock"

    logger.debug("Acquiring build lock for key: %s", cache_key[:32])

    fd = os.open(str(lock_file), os.O_RDWR | os.O_CREAT, 0o600)
    lock_acquired = False
    try:
        if timeout is not None:
            import time

            start = time.monotonic()
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    lock_acquired = True
                    break
                except BlockingIOError:
                    if time.monotonic() - start >= timeout:
                        raise TimeoutError(
                            f"Timeout waiting for build lock on {cache_key[:32]}"
                        ) from None
                    time.sleep(0.1)
        else:
            fcntl.flock(fd, fcntl.LOCK_EX)
            lock_acquired = True

        logger.debug("Build lock acquired for key: %s", cache_key[:32])
        yield
    finally:
        if lock_acquired:
            fcntl.flock(fd, fcntl.LOCK_UN)
            logger.debug("Build lock released for key: %s", cache_key[:32])
        os.close(fd)


def _get_cached_build(
    session: Session,
    cache_key: str,
) -> BuildRecord | None:
    """Find an existing successful build with the same cache key.

    Args:
        session: Database session.
        cache_key: Cache key to look up.

    Returns:
        BuildRecord if found, None otherwise.
    """
    stmt = (
        select(BuildRecord)
        .where(
            BuildRecord.cache_key == cache_key,
            BuildRecord.status == BuildStatus.SUCCEEDED.value,
        )
        .order_by(BuildRecord.id.desc())
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none()


def _create_build_record(
    session: Session,
    profile: Profile,
    imagebuilder: ImageBuilder,
    cache_key: str,
    input_snapshot: dict[str, Any],
) -> BuildRecord:
    """Create a new BuildRecord in pending state.

    Args:
        session: Database session.
        profile: Profile ORM instance.
        imagebuilder: ImageBuilder ORM instance.
        cache_key: Computed cache key.
        input_snapshot: Build input snapshot.

    Returns:
        Created BuildRecord.
    """
    build = BuildRecord(
        profile_id=profile.id,
        imagebuilder_id=imagebuilder.id,
        cache_key=cache_key,
        input_snapshot=input_snapshot,
        status=BuildStatus.PENDING.value,
    )
    session.add(build)
    session.flush()
    return build


def _create_artifact_record(
    session: Session,
    build: BuildRecord,
    artifact_info: ArtifactInfo,
    absolute_path: str | None = None,
) -> Artifact:
    """Create an Artifact record from ArtifactInfo.

    Args:
        session: Database session.
        build: Parent BuildRecord.
        artifact_info: Discovered artifact information.
        absolute_path: Optional absolute path.

    Returns:
        Created Artifact record.
    """
    artifact = Artifact(
        build_id=build.id,
        kind=artifact_info.kind,
        relative_path=artifact_info.relative_path,
        absolute_path=absolute_path,
        filename=artifact_info.filename,
        size_bytes=artifact_info.size_bytes,
        sha256=artifact_info.sha256,
        labels=artifact_info.labels,
    )
    session.add(artifact)
    return artifact


def build_or_reuse(
    session: Session,
    profile: Profile,
    profile_schema: ProfileSchema,
    imagebuilder: ImageBuilder,
    settings: Settings | None = None,
    force_rebuild: bool = False,
    extra_packages: list[str] | None = None,
    build_options: dict[str, Any] | None = None,
    base_path: Path | None = None,
) -> tuple[BuildRecord, bool]:
    """Build an image or reuse an existing build if cached.

    This is the main entry point for the build pipeline. It:
    1. Stages overlay content and computes its hash
    2. Computes the cache key from all inputs
    3. Checks for existing successful build with same cache key
    4. If not found (or force_rebuild), runs the build
    5. Persists BuildRecord and Artifact records

    Args:
        session: Database session.
        profile: Profile ORM instance.
        profile_schema: ProfileSchema for the profile.
        imagebuilder: ImageBuilder ORM instance (must be in ready state).
        settings: Application settings.
        force_rebuild: Force rebuild even if cached.
        extra_packages: Additional packages at build time.
        build_options: Additional build options.
        base_path: Base path for resolving overlay sources.

    Returns:
        Tuple of (BuildRecord, is_cache_hit).

    Raises:
        BuildServiceError: If build preparation fails.
        OverlayStagingError: If overlay staging fails.
        BuildExecutionError: If build execution fails.
    """
    if settings is None:
        settings = get_settings()

    if base_path is None:
        base_path = Path.cwd()

    # Validate Image Builder
    ib_root = Path(imagebuilder.root_dir)
    if not validate_imagebuilder_root(ib_root):
        raise BuildServiceError(
            f"Image Builder root is invalid: {ib_root}",
            code="invalid_imagebuilder",
        )

    # Stage overlay and compute hash
    overlay_hash: str | None = None
    staging_dir: Path | None = None

    if has_overlay_content(profile_schema):
        staging_dir = Path(tempfile.mkdtemp(prefix="owrt_overlay_"))
        try:
            _, overlay_hash = stage_and_hash_overlay(
                staging_dir, profile_schema, base_path
            )
            logger.info(
                "Staged overlay to %s (hash=%s)", staging_dir, overlay_hash[:16]
            )
        except OverlayStagingError:
            if staging_dir and staging_dir.exists():
                import shutil

                shutil.rmtree(staging_dir, ignore_errors=True)
            raise

    # Compute cache key
    cache_key, build_inputs = compute_cache_key_from_profile(
        profile=profile_schema,
        overlay_hash=overlay_hash,
        extra_packages=extra_packages,
        build_options=build_options,
    )
    logger.info("Computed cache key: %s", cache_key[:32])

    # Get lock directory
    lock_dir = settings.cache_dir / ".locks"

    try:
        with build_lock(lock_dir, cache_key, timeout=300):
            # Check for cached build (after acquiring lock)
            if not force_rebuild:
                cached = _get_cached_build(session, cache_key)
                if cached is not None:
                    logger.info(
                        "Cache hit for key %s, reusing build %d",
                        cache_key[:32],
                        cached.id,
                    )
                    # Update usage timestamp
                    imagebuilder.last_used_at = datetime.now(timezone.utc)
                    return cached, True

            # Create build record
            build = _create_build_record(
                session=session,
                profile=profile,
                imagebuilder=imagebuilder,
                cache_key=cache_key,
                input_snapshot=build_inputs.to_dict(),
            )
            logger.info("Created build record %d", build.id)

            # Prepare build directories
            build_id_str = f"{build.id:08d}_{uuid.uuid4().hex[:8]}"
            build_dir = (
                settings.artifacts_dir
                / profile_schema.openwrt_release
                / profile_schema.target
                / profile_schema.subtarget
                / profile_schema.profile_id
                / build_id_str
            )
            build_dir.mkdir(parents=True, exist_ok=True)

            # Update build record with paths
            build.build_dir = str(build_dir)
            build.mark_running()
            session.flush()

            try:
                # Run the build
                result = run_build(
                    profile=profile_schema,
                    imagebuilder_root=ib_root,
                    build_dir=build_dir,
                    files_dir=staging_dir,
                    extra_packages=extra_packages,
                    timeout=settings.build_timeout,
                )

                build.log_path = str(result.log_path)

                if result.success:
                    # Discover artifacts
                    artifacts = discover_artifacts(
                        result.bin_dir,
                        artifacts_root=settings.artifacts_dir,
                    )

                    # Generate and write manifest
                    manifest = generate_manifest(
                        artifacts=artifacts,
                        build_id=build.id,
                        cache_key=cache_key,
                        profile_id=profile_schema.profile_id,
                        build_inputs=build_inputs.to_dict(),
                    )
                    manifest_path = build_dir / "manifest.json"
                    write_manifest(manifest, manifest_path)

                    # Persist artifacts
                    for artifact_info in artifacts:
                        artifact_path = result.bin_dir / artifact_info.filename
                        _create_artifact_record(
                            session=session,
                            build=build,
                            artifact_info=artifact_info,
                            absolute_path=str(artifact_path)
                            if artifact_path.exists()
                            else None,
                        )

                    build.mark_succeeded()
                    imagebuilder.last_used_at = datetime.now(timezone.utc)
                    session.flush()

                    logger.info(
                        "Build %d succeeded with %d artifacts",
                        build.id,
                        len(artifacts),
                    )
                else:
                    build.mark_failed(
                        error_type="build_failed",
                        message=result.error_message,
                    )
                    session.flush()
                    logger.error("Build %d failed: %s", build.id, result.error_message)

            except BuildExecutionError as e:
                build.mark_failed(error_type=e.code, message=str(e))
                session.flush()
                raise

            return build, False

    finally:
        # Clean up staging directory
        if staging_dir and staging_dir.exists():
            import shutil

            shutil.rmtree(staging_dir, ignore_errors=True)


def get_build(session: Session, build_id: int) -> BuildRecord:
    """Get a build record by ID.

    Args:
        session: Database session.
        build_id: Build ID.

    Returns:
        BuildRecord instance.

    Raises:
        BuildNotFoundError: If build not found.
    """
    build = session.get(BuildRecord, build_id)
    if build is None:
        raise BuildNotFoundError(build_id)
    return build


def get_build_or_none(session: Session, build_id: int) -> BuildRecord | None:
    """Get a build record by ID, or None if not found.

    Args:
        session: Database session.
        build_id: Build ID.

    Returns:
        BuildRecord instance or None.
    """
    return session.get(BuildRecord, build_id)


def list_builds(
    session: Session,
    profile_id: int | None = None,
    status: BuildStatus | None = None,
    limit: int = 100,
) -> list[BuildRecord]:
    """List build records with optional filters.

    Args:
        session: Database session.
        profile_id: Filter by profile ID.
        status: Filter by status.
        limit: Maximum results to return.

    Returns:
        List of BuildRecord instances.
    """
    stmt = select(BuildRecord)

    if profile_id is not None:
        stmt = stmt.where(BuildRecord.profile_id == profile_id)
    if status is not None:
        stmt = stmt.where(BuildRecord.status == status.value)

    stmt = stmt.order_by(BuildRecord.id.desc()).limit(limit)

    return list(session.execute(stmt).scalars().all())


def get_build_artifacts(session: Session, build_id: int) -> list[Artifact]:
    """Get artifacts for a build.

    Args:
        session: Database session.
        build_id: Build ID.

    Returns:
        List of Artifact instances.

    Raises:
        BuildNotFoundError: If build not found.
    """
    build = get_build(session, build_id)
    return list(build.artifacts)


__all__ = [
    "BuildNotFoundError",
    "BuildServiceError",
    "CacheConflictError",
    "build_lock",
    "build_or_reuse",
    "get_build",
    "get_build_artifacts",
    "get_build_or_none",
    "list_builds",
]
