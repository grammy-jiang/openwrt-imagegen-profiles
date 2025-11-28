"""Image Builder service module.

This module provides high-level APIs for Image Builder management:
- ensure_builder(): Ensure an Image Builder is available
- list_builders(): List cached Image Builders
- get_builder(): Get a specific Image Builder
- prune_builders(): Remove unused/deprecated Image Builders

All operations use locking to prevent concurrent downloads of the same builder.
"""

from __future__ import annotations

import fcntl
import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from openwrt_imagegen.config import get_settings
from openwrt_imagegen.imagebuilder.fetch import (
    DownloadError,
    ExtractionError,
    VerificationError,
    download_imagebuilder,
    get_cache_size,
    prune_builder,
)
from openwrt_imagegen.imagebuilder.models import ImageBuilder
from openwrt_imagegen.types import ImageBuilderState

if TYPE_CHECKING:
    from openwrt_imagegen.config import Settings

logger = logging.getLogger(__name__)


class ImageBuilderNotFoundError(Exception):
    """Raised when an Image Builder is not found in the database."""

    def __init__(
        self,
        release: str,
        target: str,
        subtarget: str,
        code: str = "imagebuilder_not_found",
    ) -> None:
        """Initialize ImageBuilderNotFoundError.

        Args:
            release: OpenWrt release version.
            target: Target platform.
            subtarget: Subtarget.
            code: Error code for structured error handling.
        """
        super().__init__(f"Image Builder not found: {release}/{target}/{subtarget}")
        self.release = release
        self.target = target
        self.subtarget = subtarget
        self.code = code


class ImageBuilderBrokenError(Exception):
    """Raised when an Image Builder is in broken state."""

    def __init__(
        self,
        release: str,
        target: str,
        subtarget: str,
        code: str = "imagebuilder_broken",
    ) -> None:
        """Initialize ImageBuilderBrokenError.

        Args:
            release: OpenWrt release version.
            target: Target platform.
            subtarget: Subtarget.
            code: Error code for structured error handling.
        """
        super().__init__(f"Image Builder is broken: {release}/{target}/{subtarget}")
        self.release = release
        self.target = target
        self.subtarget = subtarget
        self.code = code


class OfflineModeError(Exception):
    """Raised when download is required but offline mode is enabled."""

    def __init__(
        self,
        message: str = "Cannot download in offline mode",
        code: str = "offline_mode",
    ) -> None:
        """Initialize OfflineModeError.

        Args:
            message: Error description.
            code: Error code for structured error handling.
        """
        super().__init__(message)
        self.code = code


@contextmanager
def builder_lock(
    cache_dir: Path,
    release: str,
    target: str,
    subtarget: str,
    timeout: float | None = None,
) -> Iterator[None]:
    """Acquire a lock for an Image Builder download.

    Uses a file-based lock to prevent concurrent downloads of the same builder.
    The lock file is stored in the cache directory.

    Args:
        cache_dir: Root cache directory.
        release: OpenWrt release version.
        target: Target platform.
        subtarget: Subtarget.
        timeout: Lock acquisition timeout in seconds (None = blocking).

    Yields:
        None when lock is acquired.

    Raises:
        TimeoutError: If lock cannot be acquired within timeout.
    """
    lock_dir = cache_dir / ".locks"
    lock_dir.mkdir(parents=True, exist_ok=True)

    # Sanitize components for use in filename
    safe_name = f"{release}_{target}_{subtarget}.lock".replace("/", "_")
    lock_file = lock_dir / safe_name

    logger.debug("Acquiring lock for %s/%s/%s", release, target, subtarget)

    fd = os.open(str(lock_file), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        if timeout is not None:
            # Non-blocking with timeout
            import time

            start = time.monotonic()
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError as e:
                    if time.monotonic() - start >= timeout:
                        raise TimeoutError(
                            f"Timeout waiting for lock on {release}/{target}/{subtarget}"
                        ) from e
                    time.sleep(0.1)
        else:
            # Blocking
            fcntl.flock(fd, fcntl.LOCK_EX)

        logger.debug("Lock acquired for %s/%s/%s", release, target, subtarget)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
        logger.debug("Lock released for %s/%s/%s", release, target, subtarget)


def _get_builder(
    session: Session,
    release: str,
    target: str,
    subtarget: str,
) -> ImageBuilder | None:
    """Get an Image Builder from the database.

    Args:
        session: Database session.
        release: OpenWrt release version.
        target: Target platform.
        subtarget: Subtarget.

    Returns:
        ImageBuilder instance or None if not found.
    """
    stmt = select(ImageBuilder).where(
        ImageBuilder.openwrt_release == release,
        ImageBuilder.target == target,
        ImageBuilder.subtarget == subtarget,
    )
    return session.execute(stmt).scalars().first()


def get_builder(
    session: Session,
    release: str,
    target: str,
    subtarget: str,
) -> ImageBuilder:
    """Get an Image Builder from the database.

    Args:
        session: Database session.
        release: OpenWrt release version.
        target: Target platform.
        subtarget: Subtarget.

    Returns:
        ImageBuilder instance.

    Raises:
        ImageBuilderNotFoundError: If not found in database.
    """
    builder = _get_builder(session, release, target, subtarget)
    if builder is None:
        raise ImageBuilderNotFoundError(release, target, subtarget)
    return builder


def list_builders(
    session: Session,
    release: str | None = None,
    target: str | None = None,
    subtarget: str | None = None,
    state: ImageBuilderState | None = None,
) -> list[ImageBuilder]:
    """List Image Builders in the database.

    Args:
        session: Database session.
        release: Filter by release (optional).
        target: Filter by target (optional).
        subtarget: Filter by subtarget (optional).
        state: Filter by state (optional).

    Returns:
        List of ImageBuilder instances matching the filters.
    """
    stmt = select(ImageBuilder)

    if release is not None:
        stmt = stmt.where(ImageBuilder.openwrt_release == release)
    if target is not None:
        stmt = stmt.where(ImageBuilder.target == target)
    if subtarget is not None:
        stmt = stmt.where(ImageBuilder.subtarget == subtarget)
    if state is not None:
        stmt = stmt.where(ImageBuilder.state == state.value)

    stmt = stmt.order_by(
        ImageBuilder.openwrt_release,
        ImageBuilder.target,
        ImageBuilder.subtarget,
    )

    return list(session.execute(stmt).scalars().all())


def ensure_builder(
    session: Session,
    release: str,
    target: str,
    subtarget: str,
    settings: Settings | None = None,
    force_download: bool = False,
    client: httpx.Client | None = None,
) -> ImageBuilder:
    """Ensure an Image Builder is available for use.

    This is the main entry point for Image Builder management. It:
    1. Checks if a ready builder exists in the database
    2. If not, acquires a lock and downloads/extracts the builder
    3. Creates/updates the database record
    4. Returns the ready builder

    Args:
        session: Database session.
        release: OpenWrt release version (e.g., '23.05.3' or 'snapshot').
        target: Target platform (e.g., 'ath79').
        subtarget: Subtarget (e.g., 'generic').
        settings: Application settings (uses defaults if not provided).
        force_download: Force re-download even if builder exists.
        client: HTTPX client (creates one if not provided).

    Returns:
        ImageBuilder instance in ready state.

    Raises:
        ImageBuilderBrokenError: If builder is in broken state.
        OfflineModeError: If download required but offline mode enabled.
        DownloadError: If download fails.
        VerificationError: If checksum verification fails.
        ExtractionError: If extraction fails.
    """
    if settings is None:
        settings = get_settings()

    # Check for existing builder
    builder = _get_builder(session, release, target, subtarget)

    if builder is not None and not force_download:
        if builder.state == ImageBuilderState.READY.value:
            # Verify the root_dir still exists
            if Path(builder.root_dir).exists():
                logger.info(
                    "Using cached Image Builder: %s/%s/%s",
                    release,
                    target,
                    subtarget,
                )
                # Update last_used_at
                builder.last_used_at = datetime.now(timezone.utc)
                return builder
            else:
                # Directory was deleted externally
                logger.warning(
                    "Image Builder directory missing, re-downloading: %s",
                    builder.root_dir,
                )
                builder.mark_broken()
                session.flush()

        elif builder.state == ImageBuilderState.BROKEN.value:
            if not force_download:
                raise ImageBuilderBrokenError(release, target, subtarget)

        elif builder.state == ImageBuilderState.DEPRECATED.value:
            # Allow downloading a new one
            logger.info(
                "Replacing deprecated Image Builder: %s/%s/%s",
                release,
                target,
                subtarget,
            )

    # Need to download
    if settings.offline:
        raise OfflineModeError(
            f"Cannot download Image Builder {release}/{target}/{subtarget} "
            "in offline mode"
        )

    # Acquire lock and download
    with builder_lock(settings.cache_dir, release, target, subtarget):
        # Re-check after acquiring lock (another process may have downloaded)
        builder = _get_builder(session, release, target, subtarget)
        if (
            not force_download
            and builder is not None
            and builder.state == ImageBuilderState.READY.value
            and Path(builder.root_dir).exists()
        ):
            logger.info(
                "Image Builder became available while waiting for lock: %s/%s/%s",
                release,
                target,
                subtarget,
            )
            builder.last_used_at = datetime.now(timezone.utc)
            return builder

        # Create or get builder record
        if builder is None:
            from openwrt_imagegen.imagebuilder.fetch import build_imagebuilder_url

            urls = build_imagebuilder_url(release, target, subtarget)
            builder = ImageBuilder(
                openwrt_release=release,
                target=target,
                subtarget=subtarget,
                upstream_url=urls.archive_url,
                root_dir="",  # Will be updated after extraction
                state=ImageBuilderState.PENDING.value,
            )
            session.add(builder)
            session.flush()

        # Download and extract
        manage_client = client is None
        http_client: httpx.Client = (
            httpx.Client(follow_redirects=True) if manage_client else client  # type: ignore[assignment]
        )

        try:
            root_dir, checksum = download_imagebuilder(
                http_client,
                release,
                target,
                subtarget,
                settings.cache_dir,
                verify_checksum=True,
                keep_archive=False,
            )

            # Update builder record
            builder.root_dir = str(root_dir)
            builder.checksum = checksum
            builder.mark_ready()
            now = datetime.now(timezone.utc)
            if builder.first_used_at is None:
                builder.first_used_at = now
            builder.last_used_at = now

            session.flush()

            logger.info(
                "Image Builder ready: %s/%s/%s at %s",
                release,
                target,
                subtarget,
                root_dir,
            )

            return builder

        except (DownloadError, VerificationError, ExtractionError) as e:
            builder.mark_broken()
            session.flush()
            logger.error(
                "Failed to download Image Builder %s/%s/%s: %s",
                release,
                target,
                subtarget,
                e,
            )
            raise

        finally:
            if manage_client:
                http_client.close()


def prune_builders(
    session: Session,
    deprecated_only: bool = True,
    unused_days: int | None = None,
    settings: Settings | None = None,
    dry_run: bool = False,
) -> list[tuple[str, str, str]]:
    """Prune unused or deprecated Image Builders.

    Args:
        session: Database session.
        deprecated_only: Only prune deprecated builders (safe prune).
        unused_days: Prune builders not used for this many days (aggressive).
        settings: Application settings.
        dry_run: If True, only report what would be pruned.

    Returns:
        List of (release, target, subtarget) tuples that were/would be pruned.
    """
    if settings is None:
        settings = get_settings()

    pruned: list[tuple[str, str, str]] = []

    # Build query for builders to prune
    stmt = select(ImageBuilder)

    if deprecated_only:
        stmt = stmt.where(ImageBuilder.state == ImageBuilderState.DEPRECATED.value)
    elif unused_days is not None:
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(days=unused_days)
        stmt = stmt.where(
            (ImageBuilder.last_used_at < cutoff) | (ImageBuilder.last_used_at.is_(None))
        )

    builders = list(session.execute(stmt).scalars().all())

    for builder in builders:
        key = (builder.openwrt_release, builder.target, builder.subtarget)

        if dry_run:
            logger.info(
                "[DRY RUN] Would prune Image Builder: %s/%s/%s",
                *key,
            )
            pruned.append(key)
            continue

        # Remove from filesystem
        builder_dir = (
            settings.cache_dir
            / builder.openwrt_release
            / builder.target
            / builder.subtarget
        )
        try:
            if builder_dir.exists():
                prune_builder(builder_dir)
        except OSError as e:
            logger.error("Failed to prune %s: %s", builder_dir, e)
            continue

        # Remove from database
        session.delete(builder)
        pruned.append(key)
        logger.info("Pruned Image Builder: %s/%s/%s", *key)

    if not dry_run:
        session.flush()

    return pruned


def get_builder_cache_info(
    settings: Settings | None = None,
) -> dict[str, object]:
    """Get information about the Image Builder cache.

    Args:
        settings: Application settings.

    Returns:
        Dictionary with cache information.
    """
    if settings is None:
        settings = get_settings()

    cache_dir = settings.cache_dir
    total_size = get_cache_size(cache_dir)

    return {
        "cache_dir": str(cache_dir),
        "total_size_bytes": total_size,
        "total_size_human": _format_size(total_size),
        "exists": cache_dir.exists(),
    }


def _format_size(size_bytes: int) -> str:
    """Format bytes as human-readable size."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes //= 1024
    return f"{size_bytes:.1f} PB"


__all__ = [
    "ImageBuilderBrokenError",
    "ImageBuilderNotFoundError",
    "OfflineModeError",
    "builder_lock",
    "ensure_builder",
    "get_builder",
    "get_builder_cache_info",
    "list_builders",
    "prune_builders",
]
