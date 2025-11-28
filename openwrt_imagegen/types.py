"""Shared type definitions for openwrt_imagegen.

This module contains dataclasses, TypedDicts, and type aliases shared across
subpackages to avoid circular imports.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import TypedDict


class BuildStatus(str, Enum):
    """Status of a build operation."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class FlashStatus(str, Enum):
    """Status of a flash operation."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ImageBuilderState(str, Enum):
    """State of an Image Builder instance."""

    PENDING = "pending"
    READY = "ready"
    BROKEN = "broken"
    DEPRECATED = "deprecated"


class VerificationMode(str, Enum):
    """Mode for verifying flashed images."""

    FULL = "full-hash"
    PREFIX_16M = "prefix-16MiB"
    PREFIX_64M = "prefix-64MiB"
    SKIP = "skipped"


class VerificationResult(str, Enum):
    """Result of flash verification."""

    MATCH = "match"
    MISMATCH = "mismatch"
    SKIPPED = "skipped"


class FileSpec(TypedDict, total=False):
    """Specification for a file to be overlayed into the image."""

    source: str
    destination: str
    mode: str
    owner: str


class ProfilePolicies(TypedDict, total=False):
    """Build policies for a profile."""

    filesystem: str
    include_kernel_symbols: bool
    strip_debug: bool
    auto_resize_rootfs: bool
    allow_snapshot: bool


class BuildDefaults(TypedDict, total=False):
    """Default build options for a profile."""

    rebuild_if_cached: bool
    initramfs: bool
    keep_build_dir: bool


@dataclass
class OperationResult:
    """Result of an operation (build, flash, etc.)."""

    success: bool
    message: str
    code: str | None = None
    log_path: str | None = None
    details: dict[str, object] = field(default_factory=dict)


@dataclass
class ArtifactInfo:
    """Information about a build artifact."""

    filename: str
    relative_path: str
    size_bytes: int
    sha256: str
    kind: str | None = None
    labels: list[str] = field(default_factory=list)


__all__ = [
    "ArtifactInfo",
    "BuildDefaults",
    "BuildStatus",
    "FileSpec",
    "FlashStatus",
    "ImageBuilderState",
    "OperationResult",
    "ProfilePolicies",
    "VerificationMode",
    "VerificationResult",
]
