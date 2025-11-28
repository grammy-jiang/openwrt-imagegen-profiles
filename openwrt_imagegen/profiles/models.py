"""Profile ORM model.

This module defines the Profile model for storing device build profiles
in the database. See docs/DB_MODELS.md and docs/PROFILES.md for the
schema design and field definitions.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from openwrt_imagegen.db import Base

if TYPE_CHECKING:
    from openwrt_imagegen.builds.models import BuildRecord


class Profile(Base):
    """ORM model for device build profiles.

    Profiles are immutable build recipes that describe how to build
    an OpenWrt image for a specific device. They include device ID,
    OpenWrt release, target/subtarget, package set, and optional overlays.

    Attributes:
        id: Primary key.
        profile_id: Unique string identifier (immutable after creation).
        name: Human-readable name.
        description: Optional longer description.
        device_id: Device identifier (e.g., 'tl-wdr4300-v1').
        tags: JSON array of tags for filtering.
        openwrt_release: OpenWrt release version (e.g., '23.05.3').
        target: Target platform (e.g., 'ath79').
        subtarget: Subtarget (e.g., 'generic').
        imagebuilder_profile: Image Builder profile name.
        packages: JSON array of packages to install.
        packages_remove: JSON array of packages to remove.
        files: JSON array of file overlay specifications.
        overlay_dir: Optional path to overlay directory.
        policies: JSON object with build policies.
        build_defaults: JSON object with default build options.
        bin_dir: Optional custom output directory.
        extra_image_name: Optional extra name suffix for images.
        disabled_services: JSON array of services to disable.
        rootfs_partsize: Optional root filesystem partition size.
        add_local_key: Whether to add local signing key.
        created_at: Timestamp of creation.
        updated_at: Timestamp of last update.
        created_by: Optional creator identifier.
        notes: Optional notes/comments.
    """

    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    device_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True, default=list)

    # OpenWrt Image Builder target info
    openwrt_release: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    target: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    subtarget: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    imagebuilder_profile: Mapped[str] = mapped_column(String(255), nullable=False)

    # Package configuration
    packages: Mapped[list[str] | None] = mapped_column(
        JSON, nullable=True, default=list
    )
    packages_remove: Mapped[list[str] | None] = mapped_column(
        JSON, nullable=True, default=list
    )

    # File overlays
    files: Mapped[list[dict[str, str]] | None] = mapped_column(
        JSON, nullable=True, default=list
    )
    overlay_dir: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Build policies and defaults
    policies: Mapped[dict[str, object] | None] = mapped_column(
        JSON, nullable=True, default=dict
    )
    build_defaults: Mapped[dict[str, object] | None] = mapped_column(
        JSON, nullable=True, default=dict
    )

    # Optional configuration
    bin_dir: Mapped[str | None] = mapped_column(String(500), nullable=True)
    extra_image_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    disabled_services: Mapped[list[str] | None] = mapped_column(
        JSON, nullable=True, default=list
    )
    rootfs_partsize: Mapped[int | None] = mapped_column(Integer, nullable=True)
    add_local_key: Mapped[bool | None] = mapped_column(nullable=True)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    builds: Mapped[list["BuildRecord"]] = relationship(
        "BuildRecord", back_populates="profile", lazy="dynamic"
    )

    # Indexes for common query patterns
    __table_args__ = (
        Index("ix_profiles_release_target", "openwrt_release", "target", "subtarget"),
    )

    def __repr__(self) -> str:
        """Return string representation of Profile."""
        return (
            f"<Profile(id={self.id}, profile_id='{self.profile_id}', "
            f"device_id='{self.device_id}', release='{self.openwrt_release}')>"
        )


__all__ = ["Profile"]
