"""Pydantic models for profile schema validation.

This module defines the Pydantic models for validating profile data
from YAML/JSON files before import, and for exporting profiles to
file formats.

Schema follows docs/PROFILES.md sections 2-6.
"""

import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Validation patterns from docs/PROFILES.md section 6
PROFILE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_.\-]+$")


class FileSpecSchema(BaseModel):
    """Schema for file overlay specification.

    Attributes:
        source: Path on the host (relative to profiles/ or absolute).
        destination: Path inside the image filesystem (must start with /).
        mode: Optional file mode (octal string, e.g., '0644').
        owner: Optional user:group ownership (e.g., 'root:root').
    """

    model_config = ConfigDict(extra="forbid")

    source: str = Field(description="Path to source file on host")
    destination: str = Field(
        description="Destination path in image (must start with /)"
    )
    mode: str | None = Field(
        default=None, description="File mode (octal string, e.g., '0644')"
    )
    owner: str | None = Field(
        default=None, description="File ownership (e.g., 'root:root')"
    )

    @field_validator("destination")
    @classmethod
    def validate_destination(cls, v: str) -> str:
        """Validate destination starts with /."""
        if not v.startswith("/"):
            raise ValueError("destination must start with '/'")
        return v

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str | None) -> str | None:
        """Validate mode is a valid octal string."""
        if v is None:
            return v
        # Check it's a valid octal string (e.g., 0644, 0755)
        if not re.match(r"^0?[0-7]{3,4}$", v):
            raise ValueError(
                f"mode must be a valid octal string (e.g., '0644'), got '{v}'"
            )
        return v


class ProfilePoliciesSchema(BaseModel):
    """Schema for profile build policies.

    Attributes:
        filesystem: Preferred root filesystem type (squashfs, ext4).
        include_kernel_symbols: Include kernel debug symbols.
        strip_debug: Strip debug data from packages.
        auto_resize_rootfs: Hint to resize rootfs to fill device.
        allow_snapshot: Allow targeting snapshot/unreleased builds.
    """

    model_config = ConfigDict(extra="forbid")

    filesystem: str | None = Field(default=None, description="Filesystem type")
    include_kernel_symbols: bool | None = Field(default=None)
    strip_debug: bool | None = Field(default=None)
    auto_resize_rootfs: bool | None = Field(default=None)
    allow_snapshot: bool | None = Field(default=None)

    @field_validator("filesystem")
    @classmethod
    def validate_filesystem(cls, v: str | None) -> str | None:
        """Validate filesystem is one of supported types."""
        if v is None:
            return v
        supported = {"squashfs", "ext4"}
        if v not in supported:
            raise ValueError(f"filesystem must be one of {supported}, got '{v}'")
        return v


class BuildDefaultsSchema(BaseModel):
    """Schema for default build options.

    Attributes:
        rebuild_if_cached: Force rebuild instead of reusing cached builds.
        initramfs: Build initramfs images by default.
        keep_build_dir: Keep intermediate build directories.
    """

    model_config = ConfigDict(extra="forbid")

    rebuild_if_cached: bool | None = Field(default=None)
    initramfs: bool | None = Field(default=None)
    keep_build_dir: bool | None = Field(default=None)


class ProfileMetaSchema(BaseModel):
    """Schema for profile metadata (in exported files).

    Attributes:
        created_at: Timestamp of creation.
        updated_at: Timestamp of last update.
        created_by: Creator identifier.
    """

    model_config = ConfigDict(extra="forbid")

    created_at: str | None = Field(default=None)
    updated_at: str | None = Field(default=None)
    created_by: str | None = Field(default=None)


class ProfileSchema(BaseModel):
    """Complete profile schema for validation and import/export.

    This schema mirrors the profile structure defined in docs/PROFILES.md.
    It is used for validating YAML/JSON files before import and for
    exporting profiles from the database.

    Attributes:
        profile_id: Unique stable identifier.
        name: Human-readable name.
        description: Optional longer description.
        device_id: Device identifier.
        tags: Optional tags for filtering.
        openwrt_release: OpenWrt release version.
        target: Target platform.
        subtarget: Subtarget.
        imagebuilder_profile: Image Builder profile name.
        packages: Extra packages to install.
        packages_remove: Packages to remove from defaults.
        files: File overlay specifications.
        overlay_dir: Directory of overlay files.
        policies: Build policies.
        build_defaults: Default build options.
        bin_dir: Optional custom output directory.
        extra_image_name: Optional extra name suffix for images.
        disabled_services: Services to disable in image.
        rootfs_partsize: Root filesystem partition size (MB).
        add_local_key: Add local signing key.
        created_by: Creator identifier.
        notes: Optional notes/comments.
        meta: Optional metadata section (for exports).
    """

    model_config = ConfigDict(extra="forbid")

    # Identity & device targeting
    profile_id: Annotated[
        str, Field(description="Unique stable identifier", min_length=1, max_length=255)
    ]
    name: Annotated[
        str, Field(description="Human-readable name", min_length=1, max_length=255)
    ]
    description: str | None = Field(default=None, description="Longer description")
    device_id: Annotated[
        str, Field(description="Device identifier", min_length=1, max_length=255)
    ]
    tags: list[str] | None = Field(default=None, description="Tags for filtering")

    # OpenWrt / Image Builder selection
    openwrt_release: Annotated[
        str, Field(description="OpenWrt release version", min_length=1, max_length=50)
    ]
    target: Annotated[
        str, Field(description="Target platform", min_length=1, max_length=100)
    ]
    subtarget: Annotated[
        str, Field(description="Subtarget", min_length=1, max_length=100)
    ]
    imagebuilder_profile: Annotated[
        str,
        Field(description="Image Builder profile name", min_length=1, max_length=255),
    ]

    # Packages
    packages: list[str] | None = Field(
        default=None, description="Extra packages to install"
    )
    packages_remove: list[str] | None = Field(
        default=None, description="Packages to remove"
    )

    # Files and overlays
    files: list[FileSpecSchema] | None = Field(
        default=None, description="File overlay specifications"
    )
    overlay_dir: str | None = Field(default=None, description="Overlay directory path")

    # Policies and build defaults
    policies: ProfilePoliciesSchema | None = Field(
        default=None, description="Build policies"
    )
    build_defaults: BuildDefaultsSchema | None = Field(
        default=None, description="Default build options"
    )

    # Image Builder options
    bin_dir: str | None = Field(default=None, description="Custom output directory")
    extra_image_name: str | None = Field(
        default=None, description="Extra name suffix for images"
    )
    disabled_services: list[str] | None = Field(
        default=None, description="Services to disable"
    )
    rootfs_partsize: int | None = Field(
        default=None, ge=1, description="Root filesystem partition size (MB)"
    )
    add_local_key: bool | None = Field(
        default=None, description="Add local signing key"
    )

    # Metadata
    created_by: str | None = Field(default=None, description="Creator identifier")
    notes: str | None = Field(default=None, description="Notes/comments")

    # Export-only metadata section
    meta: ProfileMetaSchema | None = Field(
        default=None, description="Metadata section (for exports)"
    )

    @field_validator("profile_id")
    @classmethod
    def validate_profile_id(cls, v: str) -> str:
        """Validate profile_id matches safe pattern."""
        if not PROFILE_ID_PATTERN.match(v):
            raise ValueError(
                f"profile_id must match pattern {PROFILE_ID_PATTERN.pattern}, got '{v}'"
            )
        return v

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str] | None) -> list[str] | None:
        """Validate tags are non-empty strings."""
        if v is None:
            return v
        for tag in v:
            if not tag or not tag.strip():
                raise ValueError("tags must be non-empty strings")
        # Reasonable limit on number of tags
        if len(v) > 50:
            raise ValueError("too many tags (max 50)")
        return v

    @field_validator("packages", "packages_remove", "disabled_services")
    @classmethod
    def validate_string_list(cls, v: list[str] | None) -> list[str] | None:
        """Validate package/service lists have valid entries."""
        if v is None:
            return v
        for item in v:
            if not item or not item.strip():
                raise ValueError("list items must be non-empty strings")
            # Packages shouldn't have whitespace in their names
            if " " in item or "\t" in item or "\n" in item:
                raise ValueError(
                    f"list items must not contain whitespace, got '{item}'"
                )
        # Reasonable limit on list size
        if len(v) > 1000:
            raise ValueError("list too large (max 1000 items)")
        return v

    def validate_snapshot_policy(self) -> None:
        """Validate snapshot policy consistency.

        If openwrt_release is 'snapshot' but allow_snapshot is not True,
        this is considered invalid per docs/PROFILES.md section 6.

        Raises:
            ValueError: If snapshot release is used without allow_snapshot.
        """
        if self.openwrt_release == "snapshot" and (
            self.policies is None or self.policies.allow_snapshot is not True
        ):
            raise ValueError(
                "openwrt_release='snapshot' requires policies.allow_snapshot=true"
            )


class ProfileImportResult(BaseModel):
    """Result of importing a single profile.

    Attributes:
        profile_id: The profile ID that was imported.
        success: Whether import succeeded.
        error: Error message if import failed.
        created: True if profile was created, False if updated.
    """

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    success: bool
    error: str | None = None
    created: bool | None = None


class ProfileBulkImportResult(BaseModel):
    """Result of bulk import operation.

    Attributes:
        total: Total number of profiles processed.
        succeeded: Number of successful imports.
        failed: Number of failed imports.
        results: Per-profile results.
    """

    model_config = ConfigDict(extra="forbid")

    total: int
    succeeded: int
    failed: int
    results: list[ProfileImportResult]


__all__ = [
    "BuildDefaultsSchema",
    "FileSpecSchema",
    "ProfileBulkImportResult",
    "ProfileImportResult",
    "ProfileMetaSchema",
    "ProfilePoliciesSchema",
    "ProfileSchema",
]
