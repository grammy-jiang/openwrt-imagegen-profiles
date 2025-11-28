"""Cache key computation for builds.

This module handles:
- Canonical input snapshot creation from profiles and options
- Deterministic hash computation over normalized inputs
- Input comparison for cache lookup

Cache keys ensure builds with identical inputs produce identical results.
See docs/BUILD_PIPELINE.md section 2 for design details.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

from openwrt_imagegen.profiles.schema import ProfileSchema

# Schema version for cache key format; bump when cache key format changes
CACHE_KEY_SCHEMA_VERSION = "1"


@dataclass
class BuildInputs:
    """Canonical representation of all build inputs.

    This structure captures all inputs that affect build output.
    It is serialized to JSON and hashed to produce the cache key.

    Attributes:
        schema_version: Version of cache key schema.
        profile_snapshot: Normalized profile data.
        imagebuilder_key: Tuple of (release, target, subtarget).
        effective_packages: Sorted list of packages to install.
        overlay_hash: Hash of staged overlay content (or None).
        build_options: Additional build options.
    """

    schema_version: str = CACHE_KEY_SCHEMA_VERSION
    profile_snapshot: dict[str, Any] = field(default_factory=dict)
    imagebuilder_key: tuple[str, str, str] = ("", "", "")
    effective_packages: list[str] = field(default_factory=list)
    overlay_hash: str | None = None
    build_options: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation suitable for JSON.
        """
        data = asdict(self)
        # Convert tuple to list for JSON
        data["imagebuilder_key"] = list(data["imagebuilder_key"])
        return data


def normalize_profile_snapshot(profile: ProfileSchema) -> dict[str, Any]:
    """Create normalized profile snapshot for cache key.

    Extracts only the fields that affect build output, normalized
    to ensure consistent hashing.

    Args:
        profile: ProfileSchema instance.

    Returns:
        Dictionary with normalized profile data.
    """
    # Include only fields that affect the build output
    snapshot: dict[str, Any] = {
        "profile_id": profile.profile_id,
        "openwrt_release": profile.openwrt_release,
        "target": profile.target,
        "subtarget": profile.subtarget,
        "imagebuilder_profile": profile.imagebuilder_profile,
    }

    # Packages - sorted for determinism
    if profile.packages:
        snapshot["packages"] = sorted(profile.packages)
    if profile.packages_remove:
        snapshot["packages_remove"] = sorted(profile.packages_remove)

    # Files are captured via overlay_hash, but store source/destination mapping
    if profile.files:
        snapshot["files"] = [
            {
                "source": f.source,
                "destination": f.destination,
                "mode": f.mode,
                "owner": f.owner,
            }
            for f in profile.files
        ]
    if profile.overlay_dir:
        snapshot["overlay_dir"] = profile.overlay_dir

    # Image Builder options
    if profile.bin_dir:
        snapshot["bin_dir"] = profile.bin_dir
    if profile.extra_image_name:
        snapshot["extra_image_name"] = profile.extra_image_name
    if profile.disabled_services:
        snapshot["disabled_services"] = sorted(profile.disabled_services)
    if profile.rootfs_partsize is not None:
        snapshot["rootfs_partsize"] = profile.rootfs_partsize
    if profile.add_local_key is not None:
        snapshot["add_local_key"] = profile.add_local_key

    # Policies that affect build
    if profile.policies:
        policies: dict[str, Any] = {}
        if profile.policies.filesystem is not None:
            policies["filesystem"] = profile.policies.filesystem
        if profile.policies.include_kernel_symbols is not None:
            policies["include_kernel_symbols"] = profile.policies.include_kernel_symbols
        if profile.policies.strip_debug is not None:
            policies["strip_debug"] = profile.policies.strip_debug
        if policies:
            snapshot["policies"] = policies

    return snapshot


def compute_effective_packages(
    profile: ProfileSchema,
    extra_packages: list[str] | None = None,
) -> list[str]:
    """Compute the effective package list for a build.

    Combines profile packages with any extra packages provided at build time.
    Packages to remove are prefixed with '-'.

    Args:
        profile: ProfileSchema instance.
        extra_packages: Additional packages to include at build time.

    Returns:
        Sorted list of effective packages (includes '-pkg' for removals).
    """
    packages: set[str] = set()

    # Add profile packages
    if profile.packages:
        packages.update(profile.packages)

    # Add extra packages
    if extra_packages:
        packages.update(extra_packages)

    # Add removals with '-' prefix
    if profile.packages_remove:
        for pkg in profile.packages_remove:
            # Remove from packages if present, then add as removal
            packages.discard(pkg)
            packages.add(f"-{pkg}")

    return sorted(packages)


def create_build_inputs(
    profile: ProfileSchema,
    overlay_hash: str | None = None,
    extra_packages: list[str] | None = None,
    build_options: dict[str, Any] | None = None,
) -> BuildInputs:
    """Create canonical build inputs from a profile and options.

    Args:
        profile: ProfileSchema instance.
        overlay_hash: Hash of staged overlay content.
        extra_packages: Additional packages at build time.
        build_options: Additional build options.

    Returns:
        BuildInputs instance with all normalized inputs.
    """
    return BuildInputs(
        schema_version=CACHE_KEY_SCHEMA_VERSION,
        profile_snapshot=normalize_profile_snapshot(profile),
        imagebuilder_key=(profile.openwrt_release, profile.target, profile.subtarget),
        effective_packages=compute_effective_packages(profile, extra_packages),
        overlay_hash=overlay_hash,
        build_options=build_options or {},
    )


def compute_cache_key(inputs: BuildInputs) -> str:
    """Compute a cache key hash from build inputs.

    The cache key is a SHA-256 hash of the canonical JSON representation
    of the build inputs.

    Args:
        inputs: BuildInputs instance.

    Returns:
        Cache key as hex string (sha256:...).
    """
    # Serialize to canonical JSON (sorted keys, no extra whitespace)
    canonical_json = json.dumps(
        inputs.to_dict(),
        sort_keys=True,
        separators=(",", ":"),
    )

    # Compute SHA-256 hash
    hash_bytes = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    return f"sha256:{hash_bytes}"


def compute_cache_key_from_profile(
    profile: ProfileSchema,
    overlay_hash: str | None = None,
    extra_packages: list[str] | None = None,
    build_options: dict[str, Any] | None = None,
) -> tuple[str, BuildInputs]:
    """Convenience function to compute cache key directly from profile.

    Args:
        profile: ProfileSchema instance.
        overlay_hash: Hash of staged overlay content.
        extra_packages: Additional packages at build time.
        build_options: Additional build options.

    Returns:
        Tuple of (cache_key, BuildInputs).
    """
    inputs = create_build_inputs(
        profile=profile,
        overlay_hash=overlay_hash,
        extra_packages=extra_packages,
        build_options=build_options,
    )
    cache_key = compute_cache_key(inputs)
    return cache_key, inputs


__all__ = [
    "CACHE_KEY_SCHEMA_VERSION",
    "BuildInputs",
    "compute_cache_key",
    "compute_cache_key_from_profile",
    "compute_effective_packages",
    "create_build_inputs",
    "normalize_profile_snapshot",
]
