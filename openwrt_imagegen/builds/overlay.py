"""Overlay staging and hashing for builds.

This module handles:
- Staging profile files and overlay_dir into a temporary FILES directory
- Computing a deterministic hash of the staged content
- Managing overlay staging lifecycle

The staged directory is passed to Image Builder via FILES=<path>.
See docs/BUILD_PIPELINE.md section 1.1 for design details.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import stat
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from openwrt_imagegen.profiles.schema import ProfileSchema

logger = logging.getLogger(__name__)

# Default file mode when not specified
DEFAULT_FILE_MODE = 0o644
DEFAULT_DIR_MODE = 0o755


class OverlayStagingError(Exception):
    """Raised when overlay staging fails."""

    def __init__(self, message: str, code: str = "overlay_staging_error") -> None:
        super().__init__(message)
        self.code = code


def parse_mode(mode_str: str | None) -> int | None:
    """Parse an octal mode string to an integer.

    Args:
        mode_str: Mode string like '0644' or '644'.

    Returns:
        Integer mode value or None if not specified.
    """
    if not mode_str:
        return None
    # Handle with or without leading '0'
    try:
        return int(mode_str, 8)
    except ValueError:
        logger.warning("Invalid mode string: %s, using default", mode_str)
        return None


def stage_file(
    source: Path,
    dest: Path,
    mode: int | None = None,
) -> None:
    """Stage a single file to the overlay directory.

    Args:
        source: Path to source file.
        dest: Destination path in staging directory.
        mode: Optional file mode (default: preserve source or 0644).

    Raises:
        OverlayStagingError: If staging fails.
    """
    try:
        # Ensure parent directory exists
        dest.parent.mkdir(parents=True, exist_ok=True)

        # Copy file content
        shutil.copy2(source, dest)

        # Apply mode if specified
        if mode is not None:
            dest.chmod(mode)

    except OSError as e:
        raise OverlayStagingError(
            f"Failed to stage file {source} -> {dest}: {e}",
            code="file_stage_error",
        ) from e


def stage_directory(
    source_dir: Path,
    dest_dir: Path,
    follow_symlinks: bool = False,
) -> None:
    """Stage an entire directory to the overlay directory.

    Copies the directory tree, resolving symlinks by copying content
    (does not follow symlinks outside the source tree).

    Args:
        source_dir: Source directory path.
        dest_dir: Destination directory in staging area.
        follow_symlinks: If True, follow symlinks; if False, copy as regular files.

    Raises:
        OverlayStagingError: If staging fails.
    """
    source_dir_resolved = source_dir.resolve()

    try:
        for item in source_dir.rglob("*"):
            rel_path = item.relative_to(source_dir)
            dest_path = dest_dir / rel_path

            # Security check: ensure symlink targets stay within source tree
            if item.is_symlink():
                target = item.resolve()
                try:
                    target.relative_to(source_dir_resolved)
                except ValueError:
                    raise OverlayStagingError(
                        f"Symlink {item} points outside source tree: {target}",
                        code="symlink_escape",
                    ) from None

            if item.is_dir() and not item.is_symlink():
                dest_path.mkdir(parents=True, exist_ok=True)
            elif item.is_file() or (item.is_symlink() and not follow_symlinks):
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                if item.is_symlink() and not follow_symlinks:
                    # Copy symlink target content
                    shutil.copy2(item.resolve(), dest_path)
                else:
                    shutil.copy2(item, dest_path)

    except OSError as e:
        raise OverlayStagingError(
            f"Failed to stage directory {source_dir}: {e}",
            code="dir_stage_error",
        ) from e


def _validate_path_within_base(path: Path, base: Path, path_type: str) -> Path:
    """Validate that a path is contained within a base directory.

    Args:
        path: Path to validate (will be resolved).
        base: Base directory (will be resolved).
        path_type: Description of the path for error messages.

    Returns:
        The resolved path.

    Raises:
        OverlayStagingError: If path escapes base directory.
    """
    resolved_path = path.resolve()
    resolved_base = base.resolve()

    try:
        resolved_path.relative_to(resolved_base)
    except ValueError:
        raise OverlayStagingError(
            f"{path_type} path traversal detected: {path} resolves outside {base}",
            code="path_traversal",
        ) from None

    return resolved_path


def stage_overlay(
    staging_dir: Path,
    profile: ProfileSchema,
    base_path: Path | None = None,
) -> Path:
    """Stage overlay content from a profile to a temporary directory.

    Args:
        staging_dir: Directory to stage content into.
        profile: ProfileSchema with files and overlay_dir.
        base_path: Base path for resolving relative source paths.
                   Defaults to current working directory.

    Returns:
        Path to the staged directory (staging_dir).

    Raises:
        OverlayStagingError: If staging fails or path traversal detected.
    """
    if base_path is None:
        base_path = Path.cwd()

    # Resolve base_path to absolute for security checks
    base_path_resolved = base_path.resolve()

    staging_dir.mkdir(parents=True, exist_ok=True)
    staging_dir_resolved = staging_dir.resolve()

    # Stage overlay_dir first (files can override)
    if profile.overlay_dir:
        overlay_path = base_path / profile.overlay_dir

        # Security: validate overlay_dir doesn't escape base_path
        _validate_path_within_base(overlay_path, base_path_resolved, "overlay_dir")

        if not overlay_path.exists():
            raise OverlayStagingError(
                f"Overlay directory not found: {overlay_path}",
                code="overlay_not_found",
            )
        if not overlay_path.is_dir():
            raise OverlayStagingError(
                f"Overlay path is not a directory: {overlay_path}",
                code="overlay_not_dir",
            )

        logger.debug("Staging overlay_dir: %s", overlay_path)
        stage_directory(overlay_path, staging_dir)

    # Stage individual files (may override overlay_dir content)
    if profile.files:
        for file_spec in profile.files:
            source_path = base_path / file_spec.source

            # Security: validate source doesn't escape base_path
            _validate_path_within_base(source_path, base_path_resolved, "source")

            if not source_path.exists():
                raise OverlayStagingError(
                    f"Source file not found: {source_path}",
                    code="source_not_found",
                )

            # Destination is absolute path in image, convert to relative
            dest_rel = file_spec.destination.lstrip("/")
            dest_path = staging_dir / dest_rel

            # Security: validate destination doesn't escape staging_dir
            _validate_path_within_base(dest_path, staging_dir_resolved, "destination")

            mode = parse_mode(file_spec.mode)
            logger.debug(
                "Staging file: %s -> %s (mode=%s)",
                source_path,
                dest_path,
                file_spec.mode,
            )
            stage_file(source_path, dest_path, mode)

    return staging_dir


def compute_tree_hash(directory: Path) -> str:
    """Compute a deterministic hash of a directory tree.

    The hash is computed over:
    - Sorted file paths (relative to directory)
    - File contents
    - File modes (lower 9 bits: rwxrwxrwx)

    Args:
        directory: Directory to hash.

    Returns:
        SHA-256 hex digest of the tree.
    """
    hasher = hashlib.sha256()

    if not directory.exists():
        return hasher.hexdigest()

    # Collect all files with their metadata
    entries: list[tuple[str, bytes, int]] = []

    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue

        rel_path = path.relative_to(directory).as_posix()
        content = path.read_bytes()
        mode = stat.S_IMODE(path.stat().st_mode)

        entries.append((rel_path, content, mode))

    # Hash entries in sorted order
    for rel_path, content, mode in entries:
        # Hash: path\0mode\0content
        hasher.update(rel_path.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(f"{mode:o}".encode())
        hasher.update(b"\0")
        hasher.update(content)
        hasher.update(b"\0")

    return hasher.hexdigest()


def stage_and_hash_overlay(
    staging_dir: Path,
    profile: ProfileSchema,
    base_path: Path | None = None,
) -> tuple[Path, str]:
    """Stage overlay content and compute its hash.

    Convenience function that combines staging and hashing.

    Args:
        staging_dir: Directory to stage content into.
        profile: ProfileSchema with files and overlay_dir.
        base_path: Base path for resolving relative source paths.

    Returns:
        Tuple of (staging_dir, tree_hash).

    Raises:
        OverlayStagingError: If staging fails.
    """
    staged_path = stage_overlay(staging_dir, profile, base_path)
    tree_hash = compute_tree_hash(staged_path)
    return staged_path, tree_hash


def has_overlay_content(profile: ProfileSchema) -> bool:
    """Check if a profile has any overlay content to stage.

    Args:
        profile: ProfileSchema instance.

    Returns:
        True if profile has files or overlay_dir.
    """
    return bool(profile.files or profile.overlay_dir)


__all__ = [
    "DEFAULT_DIR_MODE",
    "DEFAULT_FILE_MODE",
    "OverlayStagingError",
    "compute_tree_hash",
    "has_overlay_content",
    "parse_mode",
    "stage_and_hash_overlay",
    "stage_directory",
    "stage_file",
    "stage_overlay",
]
