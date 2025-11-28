"""ImageBuilder ORM model.

This module defines the ImageBuilder model for storing cached Image Builder
instances in the database. See docs/DB_MODELS.md for the schema design.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from openwrt_imagegen.db import Base
from openwrt_imagegen.types import ImageBuilderState

if TYPE_CHECKING:
    from openwrt_imagegen.builds.models import BuildRecord


class ImageBuilder(Base):
    """ORM model for cached OpenWrt Image Builder instances.

    Each record represents a locally cached instance of an official OpenWrt
    Image Builder for a specific (release, target, subtarget) combination.

    Attributes:
        id: Primary key.
        openwrt_release: OpenWrt release version (e.g., '23.05.3').
        target: Target platform (e.g., 'ath79').
        subtarget: Subtarget (e.g., 'generic').
        upstream_url: URL where the Image Builder was downloaded from.
        archive_path: Local path to the downloaded archive (if retained).
        root_dir: Local path to the extracted Image Builder root.
        checksum: SHA-256 checksum of the downloaded archive.
        signature_verified: Whether GPG signature was verified.
        state: Current state (pending, ready, broken, deprecated).
        first_used_at: Timestamp of first use in a build.
        last_used_at: Timestamp of most recent use in a build.
    """

    __tablename__ = "imagebuilders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # OpenWrt target identification (unique key)
    openwrt_release: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    target: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    subtarget: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Download and storage info
    upstream_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    archive_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    root_dir: Mapped[str] = mapped_column(String(500), nullable=False)

    # Verification
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    signature_verified: Mapped[bool] = mapped_column(nullable=False, default=False)

    # State management
    state: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ImageBuilderState.PENDING.value
    )

    # Usage tracking
    first_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    builds: Mapped[list["BuildRecord"]] = relationship(
        "BuildRecord", back_populates="imagebuilder", lazy="dynamic"
    )

    # Indexes for common query patterns
    __table_args__ = (
        Index(
            "ix_imagebuilders_release_target_subtarget",
            "openwrt_release",
            "target",
            "subtarget",
            unique=True,
        ),
    )

    def __repr__(self) -> str:
        """Return string representation of ImageBuilder."""
        return (
            f"<ImageBuilder(id={self.id}, release='{self.openwrt_release}', "
            f"target='{self.target}', subtarget='{self.subtarget}', "
            f"state='{self.state}')>"
        )

    def mark_ready(self) -> None:
        """Mark this Image Builder as ready for use."""
        self.state = ImageBuilderState.READY.value

    def mark_broken(self) -> None:
        """Mark this Image Builder as broken."""
        self.state = ImageBuilderState.BROKEN.value

    def mark_deprecated(self) -> None:
        """Mark this Image Builder as deprecated."""
        self.state = ImageBuilderState.DEPRECATED.value

    def is_ready(self) -> bool:
        """Check if this Image Builder is ready for use."""
        return self.state == ImageBuilderState.READY.value


__all__ = ["ImageBuilder"]
