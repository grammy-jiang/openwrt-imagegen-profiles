"""Flash ORM models.

This module defines the FlashRecord model for tracking write operations
of artifacts to TF/SD cards. See docs/DB_MODELS.md and docs/SAFETY.md
for the schema design and safety requirements.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from openwrt_imagegen.db import Base
from openwrt_imagegen.types import FlashStatus

if TYPE_CHECKING:
    from openwrt_imagegen.builds.models import Artifact, BuildRecord


class FlashRecord(Base):
    """ORM model for TF/SD card flash operations.

    A FlashRecord tracks writing a specific artifact to a specific device.
    This provides an audit trail for flash operations and supports fleet
    management use cases.

    Attributes:
        id: Primary key.
        artifact_id: Foreign key to Artifact.
        build_id: Foreign key to BuildRecord (denormalized for queries).
        device_path: Block device path (e.g., '/dev/sdX').
        device_model: Optional device model identifier.
        device_serial: Optional device serial number.
        requested_at: Timestamp when flash was requested.
        started_at: Timestamp when flash started.
        finished_at: Timestamp when flash finished.
        status: Flash status (pending, running, succeeded, failed).
        wiped_before_flash: Whether device was wiped before flashing.
        verification_mode: Verification mode used (full-hash, prefix-64MiB, etc.).
        verification_result: Result of verification (match, mismatch, skipped).
        log_path: Path to flash operation log file.
        error_type: Type of error if flash failed.
        error_message: Error message if flash failed.
    """

    __tablename__ = "flash_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign keys
    artifact_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("artifacts.id"), nullable=False, index=True
    )
    build_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("build_records.id"), nullable=False, index=True
    )

    # Device identification
    device_path: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    device_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    device_serial: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Timing
    requested_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Status
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=FlashStatus.PENDING.value, index=True
    )

    # Flash options
    wiped_before_flash: Mapped[bool] = mapped_column(nullable=False, default=False)
    verification_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    verification_result: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Logging and errors
    log_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    artifact: Mapped["Artifact"] = relationship(
        "Artifact", back_populates="flash_records"
    )
    build: Mapped["BuildRecord"] = relationship(
        "BuildRecord", back_populates="flash_records"
    )

    # Indexes
    __table_args__ = (
        Index("ix_flash_records_artifact_status", "artifact_id", "status"),
    )

    def __repr__(self) -> str:
        """Return string representation of FlashRecord."""
        return (
            f"<FlashRecord(id={self.id}, artifact_id={self.artifact_id}, "
            f"device_path='{self.device_path}', status='{self.status}')>"
        )

    def mark_running(self) -> None:
        """Mark this flash as running."""
        self.status = FlashStatus.RUNNING.value
        self.started_at = datetime.now()

    def mark_succeeded(self) -> None:
        """Mark this flash as succeeded."""
        self.status = FlashStatus.SUCCEEDED.value
        self.finished_at = datetime.now()

    def mark_failed(
        self, error_type: str | None = None, message: str | None = None
    ) -> None:
        """Mark this flash as failed.

        Args:
            error_type: Type/category of the error.
            message: Error message details.
        """
        self.status = FlashStatus.FAILED.value
        self.finished_at = datetime.now()
        if error_type:
            self.error_type = error_type
        if message:
            self.error_message = message

    def is_succeeded(self) -> bool:
        """Check if this flash succeeded."""
        return self.status == FlashStatus.SUCCEEDED.value


__all__ = ["FlashRecord"]
