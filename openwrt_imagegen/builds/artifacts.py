"""Artifact discovery and manifest generation.

This module handles:
- Discovering build output files from Image Builder
- Classifying artifact types (sysupgrade, factory, etc.)
- Computing checksums
- Generating build manifests

See docs/BUILD_PIPELINE.md section 8 for design details.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openwrt_imagegen.types import ArtifactInfo

logger = logging.getLogger(__name__)

# File patterns for artifact classification (lowercase for case-insensitive matching)
SYSUPGRADE_PATTERNS = ["-sysupgrade.bin", "-sysupgrade.img.gz"]
FACTORY_PATTERNS = ["-factory.bin", "-factory.img", "-kernel.bin"]
KERNEL_PATTERNS = ["-kernel.bin", "-uimage", "-vmlinux"]  # lowercase patterns
ROOTFS_PATTERNS = ["-rootfs.tar.gz", "-rootfs.squashfs", "-rootfs.ext4"]
MANIFEST_PATTERNS = [".manifest"]
INITRAMFS_PATTERNS = ["-initramfs-kernel.bin", "-initramfs.bin"]

# Default chunk size for hashing
HASH_CHUNK_SIZE = 64 * 1024  # 64KB


def classify_artifact(filename: str) -> str:
    """Classify an artifact by its filename pattern.

    Args:
        filename: The artifact filename.

    Returns:
        Artifact kind (sysupgrade, factory, kernel, rootfs, manifest, initramfs, other).
    """
    filename_lower = filename.lower()

    if any(p in filename_lower for p in SYSUPGRADE_PATTERNS):
        return "sysupgrade"
    # Check initramfs BEFORE factory since -initramfs-kernel.bin could match -kernel.bin
    if any(p in filename_lower for p in INITRAMFS_PATTERNS):
        return "initramfs"
    if any(p in filename_lower for p in FACTORY_PATTERNS):
        return "factory"
    if any(p in filename_lower for p in KERNEL_PATTERNS):
        return "kernel"
    if any(p in filename_lower for p in ROOTFS_PATTERNS):
        return "rootfs"
    if any(p in filename_lower for p in MANIFEST_PATTERNS):
        return "manifest"

    return "other"


def compute_file_hash(
    file_path: Path,
    chunk_size: int = HASH_CHUNK_SIZE,
) -> str:
    """Compute SHA-256 hash of a file.

    Args:
        file_path: Path to the file.
        chunk_size: Size of chunks for streaming hash.

    Returns:
        SHA-256 hex digest.
    """
    sha256 = hashlib.sha256()
    with file_path.open("rb") as f:
        while chunk := f.read(chunk_size):
            sha256.update(chunk)
    return sha256.hexdigest()


def discover_artifacts(
    bin_dir: Path,
    artifacts_root: Path | None = None,
    include_non_binary: bool = False,
) -> list[ArtifactInfo]:
    """Discover artifacts in a build output directory.

    Args:
        bin_dir: Directory containing build outputs.
        artifacts_root: Root directory for computing relative paths.
                        If None, uses bin_dir.
        include_non_binary: Include non-binary files like .buildinfo.

    Returns:
        List of ArtifactInfo for discovered artifacts.
    """
    if not bin_dir.exists():
        logger.warning("Build output directory does not exist: %s", bin_dir)
        return []

    if artifacts_root is None:
        artifacts_root = bin_dir

    artifacts: list[ArtifactInfo] = []

    # Extensions to include
    binary_extensions = {".bin", ".img", ".gz", ".tar", ".squashfs", ".ext4"}
    other_extensions = (
        {".manifest", ".buildinfo", ".json"} if include_non_binary else set()
    )
    valid_extensions = binary_extensions | other_extensions

    # Walk the directory tree
    for path in sorted(bin_dir.rglob("*")):
        if not path.is_file():
            continue

        # Check extension
        suffix = path.suffix.lower()
        # Handle double extensions like .img.gz
        if suffix == ".gz" and path.stem.endswith(".img"):
            # This is valid
            pass
        elif suffix not in valid_extensions:
            continue

        # Skip very small files (likely not real images)
        size_bytes = path.stat().st_size
        if size_bytes < 1024 and suffix not in other_extensions:
            logger.debug("Skipping small file: %s (%d bytes)", path.name, size_bytes)
            continue

        # Compute hash and classify
        sha256 = compute_file_hash(path)
        kind = classify_artifact(path.name)

        try:
            relative_path = path.relative_to(artifacts_root).as_posix()
        except ValueError:
            relative_path = path.name

        artifact = ArtifactInfo(
            filename=path.name,
            relative_path=relative_path,
            size_bytes=size_bytes,
            sha256=sha256,
            kind=kind,
            labels=[],
        )

        # Add labels based on kind
        if kind == "sysupgrade":
            artifact.labels.append("for_tf_flash")
        if kind == "factory":
            artifact.labels.append("for_factory_install")

        artifacts.append(artifact)
        logger.debug(
            "Discovered artifact: %s (kind=%s, size=%d)",
            path.name,
            kind,
            size_bytes,
        )

    logger.info("Discovered %d artifacts in %s", len(artifacts), bin_dir)
    return artifacts


def generate_manifest(
    artifacts: list[ArtifactInfo],
    build_id: int | None = None,
    cache_key: str | None = None,
    profile_id: str | None = None,
    build_inputs: dict[str, Any] | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate a build manifest.

    The manifest contains:
    - List of artifacts with metadata
    - Build identification (ID, cache key, profile)
    - Timestamps
    - Optional extra metadata

    Args:
        artifacts: List of discovered artifacts.
        build_id: Optional database build ID.
        cache_key: Optional cache key.
        profile_id: Optional profile ID.
        build_inputs: Optional build inputs dictionary.
        extra_metadata: Optional additional metadata.

    Returns:
        Manifest dictionary suitable for JSON serialization.
    """
    now = datetime.now(timezone.utc)

    manifest: dict[str, Any] = {
        "version": "1.0",
        "generated_at": now.isoformat(),
        "artifacts": [asdict(a) for a in artifacts],
    }

    if build_id is not None:
        manifest["build_id"] = build_id
    if cache_key:
        manifest["cache_key"] = cache_key
    if profile_id:
        manifest["profile_id"] = profile_id
    if build_inputs:
        manifest["build_inputs"] = build_inputs
    if extra_metadata:
        manifest["metadata"] = extra_metadata

    # Summary statistics
    manifest["summary"] = {
        "total_artifacts": len(artifacts),
        "total_size_bytes": sum(a.size_bytes for a in artifacts),
        "kinds": list({a.kind for a in artifacts if a.kind}),
    }

    return manifest


def write_manifest(
    manifest: dict[str, Any],
    output_path: Path,
) -> Path:
    """Write manifest to a JSON file.

    Args:
        manifest: Manifest dictionary.
        output_path: Output file path.

    Returns:
        Path to written manifest file.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)

    logger.info("Wrote manifest to %s", output_path)
    return output_path


def discover_and_manifest(
    bin_dir: Path,
    manifest_path: Path,
    build_id: int | None = None,
    cache_key: str | None = None,
    profile_id: str | None = None,
    build_inputs: dict[str, Any] | None = None,
    artifacts_root: Path | None = None,
) -> tuple[list[ArtifactInfo], dict[str, Any]]:
    """Discover artifacts and generate manifest in one step.

    Args:
        bin_dir: Directory containing build outputs.
        manifest_path: Path for manifest file.
        build_id: Optional database build ID.
        cache_key: Optional cache key.
        profile_id: Optional profile ID.
        build_inputs: Optional build inputs dictionary.
        artifacts_root: Root directory for computing relative paths.

    Returns:
        Tuple of (artifacts list, manifest dict).
    """
    artifacts = discover_artifacts(bin_dir, artifacts_root=artifacts_root)

    manifest = generate_manifest(
        artifacts=artifacts,
        build_id=build_id,
        cache_key=cache_key,
        profile_id=profile_id,
        build_inputs=build_inputs,
    )

    write_manifest(manifest, manifest_path)

    return artifacts, manifest


def get_primary_artifact(artifacts: list[ArtifactInfo]) -> ArtifactInfo | None:
    """Get the primary artifact for flashing (usually sysupgrade).

    Args:
        artifacts: List of artifacts.

    Returns:
        The primary artifact, or None if not found.
    """
    # Prefer sysupgrade, then factory
    for kind in ("sysupgrade", "factory"):
        for artifact in artifacts:
            if artifact.kind == kind:
                return artifact

    # Fall back to any binary artifact
    for artifact in artifacts:
        if artifact.kind not in ("manifest", "other"):
            return artifact

    return None


__all__ = [
    "FACTORY_PATTERNS",
    "HASH_CHUNK_SIZE",
    "INITRAMFS_PATTERNS",
    "KERNEL_PATTERNS",
    "MANIFEST_PATTERNS",
    "ROOTFS_PATTERNS",
    "SYSUPGRADE_PATTERNS",
    "classify_artifact",
    "compute_file_hash",
    "discover_and_manifest",
    "discover_artifacts",
    "generate_manifest",
    "get_primary_artifact",
    "write_manifest",
]
