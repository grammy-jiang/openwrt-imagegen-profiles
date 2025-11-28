"""Build ORM models.

This module defines the BuildRecord and Artifact models for storing
build execution records and output artifacts in the database.
See docs/DB_MODELS.md for the schema design.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from openwrt_imagegen.db import Base
from openwrt_imagegen.types import BuildStatus

if TYPE_CHECKING:
    from openwrt_imagegen.flash.models import FlashRecord
    from openwrt_imagegen.imagebuilder.models import ImageBuilder
    from openwrt_imagegen.profiles.models import Profile


class BuildRecord(Base):
    """ORM model for build execution records.

    A BuildRecord captures a single build pipeline execution, including
    the profile used, Image Builder, build status, input snapshot for
    cache key computation, and references to output artifacts.

    Attributes:
        id: Primary key.
        profile_id: Foreign key to Profile.
        imagebuilder_id: Foreign key to ImageBuilder.
        status: Build status (pending, running, succeeded, failed).
        requested_at: Timestamp when build was requested.
        started_at: Timestamp when build started executing.
        finished_at: Timestamp when build finished.
        input_snapshot: JSON representation of all build inputs.
        cache_key: Hash of input_snapshot for cache lookup.
        build_dir: Path to working directory (if retained).
        log_path: Path to build log file.
        error_type: Type of error if build failed.
        error_message: Error message if build failed.
        is_cache_hit: Whether this build reused cached artifacts.
    """

    __tablename__ = "build_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign keys
    profile_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("profiles.id"), nullable=False, index=True
    )
    imagebuilder_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("imagebuilders.id"), nullable=False, index=True
    )

    # Status and timing
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=BuildStatus.PENDING.value, index=True
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Cache key and input snapshot
    input_snapshot: Mapped[dict[str, object] | None] = mapped_column(
        JSON, nullable=True
    )
    cache_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    # Build paths
    build_dir: Mapped[str | None] = mapped_column(String(500), nullable=True)
    log_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Error tracking
    error_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Cache hit indicator
    is_cache_hit: Mapped[bool] = mapped_column(nullable=False, default=False)

    # Relationships
    profile: Mapped["Profile"] = relationship("Profile", back_populates="builds")
    imagebuilder: Mapped["ImageBuilder"] = relationship(
        "ImageBuilder", back_populates="builds"
    )
    artifacts: Mapped[list["Artifact"]] = relationship(
        "Artifact", back_populates="build", cascade="all, delete-orphan"
    )
    flash_records: Mapped[list["FlashRecord"]] = relationship(
        "FlashRecord", back_populates="build", lazy="dynamic"
    )

    # Indexes
    __table_args__ = (Index("ix_build_records_profile_status", "profile_id", "status"),)

    def __repr__(self) -> str:
        """Return string representation of BuildRecord."""
        return (
            f"<BuildRecord(id={self.id}, profile_id={self.profile_id}, "
            f"status='{self.status}', cache_key='{self.cache_key[:16]}...')>"
        )

    def mark_running(self) -> None:
        """Mark this build as running."""
        self.status = BuildStatus.RUNNING.value
        self.started_at = datetime.now()

    def mark_succeeded(self) -> None:
        """Mark this build as succeeded."""
        self.status = BuildStatus.SUCCEEDED.value
        self.finished_at = datetime.now()

    def mark_failed(
        self, error_type: str | None = None, message: str | None = None
    ) -> None:
        """Mark this build as failed.

        Args:
            error_type: Type/category of the error.
            message: Error message details.
        """
        self.status = BuildStatus.FAILED.value
        self.finished_at = datetime.now()
        if error_type:
            self.error_type = error_type
        if message:
            self.error_message = message

    def is_succeeded(self) -> bool:
        """Check if this build succeeded."""
        return self.status == BuildStatus.SUCCEEDED.value


class Artifact(Base):
    """ORM model for build output artifacts.

    An Artifact represents a single file produced by a build, such as
    a sysupgrade image, factory image, or manifest file.

    Attributes:
        id: Primary key.
        build_id: Foreign key to BuildRecord.
        kind: Type of artifact (sysupgrade, factory, manifest, other).
        relative_path: Path relative to artifacts root.
        absolute_path: Full filesystem path (may be derived).
        filename: Artifact filename.
        size_bytes: File size in bytes.
        sha256: SHA-256 hash of the file.
        labels: JSON array of labels (e.g., 'for_tf_flash').
    """

    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key
    build_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("build_records.id"), nullable=False, index=True
    )

    # Artifact classification
    kind: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)

    # Paths
    relative_path: Mapped[str] = mapped_column(String(500), nullable=False)
    absolute_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)

    # File metadata
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    # Labels for filtering
    labels: Mapped[list[str] | None] = mapped_column(JSON, nullable=True, default=list)

    # Relationships
    build: Mapped["BuildRecord"] = relationship(
        "BuildRecord", back_populates="artifacts"
    )
    flash_records: Mapped[list["FlashRecord"]] = relationship(
        "FlashRecord", back_populates="artifact", lazy="dynamic"
    )

    def __repr__(self) -> str:
        """Return string representation of Artifact."""
        return (
            f"<Artifact(id={self.id}, filename='{self.filename}', "
            f"kind='{self.kind}', size={self.size_bytes})>"
        )


__all__ = ["Artifact", "BuildRecord"]
