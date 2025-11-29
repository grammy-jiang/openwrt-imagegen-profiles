"""Pydantic schemas for MCP tool responses.

These schemas define the structured output formats for MCP tools,
ensuring consistent JSON responses across all tools.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict


class ProfileSummary(BaseModel):
    """Summary of a profile for list responses."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    name: str
    device_id: str
    openwrt_release: str
    target: str
    subtarget: str
    tags: list[str] | None = None


class ProfileDetail(ProfileSummary):
    """Full profile details."""

    model_config = ConfigDict(extra="forbid")

    description: str | None = None
    imagebuilder_profile: str
    packages: list[str] | None = None
    packages_remove: list[str] | None = None
    overlay_dir: str | None = None
    policies: dict[str, Any] | None = None
    build_defaults: dict[str, Any] | None = None
    disabled_services: list[str] | None = None
    rootfs_partsize: int | None = None
    notes: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ListProfilesResponse(BaseModel):
    """Response for list_profiles tool."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    profiles: list[ProfileSummary]
    total: int
    error: dict[str, Any] | None = None


class GetProfileResponse(BaseModel):
    """Response for get_profile tool."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    profile: ProfileDetail | None = None
    error: dict[str, Any] | None = None


class ArtifactSummary(BaseModel):
    """Summary of a build artifact."""

    model_config = ConfigDict(extra="forbid")

    id: int
    filename: str
    kind: str | None = None
    size_bytes: int
    sha256: str
    relative_path: str


class BuildSummary(BaseModel):
    """Summary of a build record."""

    model_config = ConfigDict(extra="forbid")

    id: int
    profile_id: str | None
    status: str
    cache_key: str | None
    is_cache_hit: bool
    requested_at: str | None
    started_at: str | None
    finished_at: str | None
    artifact_count: int
    error_type: str | None = None
    error_message: str | None = None
    log_path: str | None = None


class BuildImageResponse(BaseModel):
    """Response for build_image tool."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    build_id: int | None = None
    cache_hit: bool = False
    status: str | None = None
    artifacts: list[ArtifactSummary] | None = None
    log_path: str | None = None
    error: dict[str, Any] | None = None


class BuildBatchResultItem(BaseModel):
    """Result for a single profile in batch build."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    build_id: int | None = None
    success: bool
    is_cache_hit: bool = False
    artifacts: list[dict[str, Any]] | None = None
    error_code: str | None = None
    error_message: str | None = None
    log_path: str | None = None


class BuildBatchResponse(BaseModel):
    """Response for build_images_batch tool."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    total: int
    succeeded: int
    failed: int
    cache_hits: int
    mode: str
    stopped_early: bool = False
    results: list[BuildBatchResultItem]
    error: dict[str, Any] | None = None


class ListBuildsResponse(BaseModel):
    """Response for list_builds tool."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    builds: list[BuildSummary]
    total: int
    error: dict[str, Any] | None = None


class ListArtifactsResponse(BaseModel):
    """Response for list_artifacts tool."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    artifacts: list[ArtifactSummary]
    total: int
    error: dict[str, Any] | None = None


class FlashResponse(BaseModel):
    """Response for flash_artifact tool."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    flash_record_id: int | None = None
    image_path: str | None = None
    device_path: str | None = None
    bytes_written: int = 0
    source_hash: str | None = None
    device_hash: str | None = None
    verification_mode: str | None = None
    verification_result: str | None = None
    message: str | None = None
    error: dict[str, Any] | None = None


__all__ = [
    "ArtifactSummary",
    "BuildBatchResponse",
    "BuildBatchResultItem",
    "BuildImageResponse",
    "BuildSummary",
    "FlashResponse",
    "GetProfileResponse",
    "ListArtifactsResponse",
    "ListBuildsResponse",
    "ListProfilesResponse",
    "ProfileDetail",
    "ProfileSummary",
]
