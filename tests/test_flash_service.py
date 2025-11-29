"""Tests for flash/service.py - flash service layer."""

import hashlib
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from openwrt_imagegen.flash.service import (
    ArtifactFileNotFoundError,
    ArtifactNotFoundError,
    FlashPlan,
    FlashResult,
    flash_artifact,
    flash_image,
    get_flash_records,
    plan_flash,
)
from openwrt_imagegen.types import FlashStatus, VerificationMode, VerificationResult


class TestPlanFlash:
    """Tests for plan_flash function."""

    def test_plan_basic(self):
        """Create basic flash plan."""
        image_content = b"Test image content"

        with tempfile.NamedTemporaryFile(delete=False, suffix=".img") as img:
            img.write(image_content)
            img.flush()

            try:
                # Mock device validation
                with patch(
                    "openwrt_imagegen.flash.service.validate_device"
                ) as mock_validate:
                    mock_validate.return_value = MagicMock(
                        path="/dev/sdb",
                        is_block_device=True,
                        is_whole_device=True,
                        is_mounted=False,
                        mount_points=[],
                        size_bytes=4000000000,
                        model=None,
                        serial=None,
                    )

                    plan = plan_flash(
                        img.name,
                        "/dev/sdb",
                        verification_mode=VerificationMode.FULL,
                    )

                    assert isinstance(plan, FlashPlan)
                    assert plan.image_path == img.name
                    assert plan.image_size == len(image_content)
                    assert plan.device_path == "/dev/sdb"
                    assert plan.wipe_before is False
                    assert plan.verification_mode == VerificationMode.FULL

                    # Hash should be computed
                    expected_hash = hashlib.sha256(image_content).hexdigest()
                    assert plan.image_hash == expected_hash
            finally:
                os.unlink(img.name)

    def test_plan_with_wipe(self):
        """Create flash plan with wipe option."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".img") as img:
            img.write(b"Content")
            img.flush()

            try:
                with patch(
                    "openwrt_imagegen.flash.service.validate_device"
                ) as mock_validate:
                    mock_validate.return_value = MagicMock(
                        path="/dev/sdb",
                        is_block_device=True,
                        is_whole_device=True,
                        is_mounted=False,
                        mount_points=[],
                        size_bytes=1000000,
                        model=None,
                        serial=None,
                    )

                    plan = plan_flash(
                        img.name,
                        "/dev/sdb",
                        wipe_before=True,
                    )

                    assert plan.wipe_before is True
            finally:
                os.unlink(img.name)

    def test_plan_skip_verification(self):
        """Plan with skipped verification has empty hash."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".img") as img:
            img.write(b"Content")
            img.flush()

            try:
                with patch(
                    "openwrt_imagegen.flash.service.validate_device"
                ) as mock_validate:
                    mock_validate.return_value = MagicMock(
                        path="/dev/sdb",
                        is_block_device=True,
                        is_whole_device=True,
                        is_mounted=False,
                        mount_points=[],
                        size_bytes=1000000,
                        model=None,
                        serial=None,
                    )

                    plan = plan_flash(
                        img.name,
                        "/dev/sdb",
                        verification_mode=VerificationMode.SKIP,
                    )

                    assert plan.image_hash == ""
                    assert plan.verification_mode == VerificationMode.SKIP
            finally:
                os.unlink(img.name)

    def test_plan_image_not_found(self):
        """Raise error for missing image."""
        from openwrt_imagegen.flash.writer import ImageNotFoundError

        with pytest.raises(ImageNotFoundError):
            plan_flash("/nonexistent/image.img", "/dev/sdb")

    def test_plan_device_validation_error(self):
        """Raise device validation errors."""
        from openwrt_imagegen.flash.device import DeviceNotFoundError

        with tempfile.NamedTemporaryFile(delete=False, suffix=".img") as img:
            img.write(b"Content")
            img.flush()

            try:
                with (
                    patch(
                        "openwrt_imagegen.flash.service.validate_device",
                        side_effect=DeviceNotFoundError("/dev/nonexistent"),
                    ),
                    pytest.raises(DeviceNotFoundError),
                ):
                    plan_flash(img.name, "/dev/nonexistent")
            finally:
                os.unlink(img.name)


class TestFlashImage:
    """Tests for flash_image function."""

    def test_dry_run_mode(self):
        """Dry run should validate but not write."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".img") as img:
            img.write(b"Test content")
            img.flush()

            try:
                with patch(
                    "openwrt_imagegen.flash.service.validate_device"
                ) as mock_validate:
                    mock_validate.return_value = MagicMock(
                        path="/dev/sdb",
                        is_block_device=True,
                        is_whole_device=True,
                        is_mounted=False,
                        mount_points=[],
                        size_bytes=1000000,
                        model=None,
                        serial=None,
                    )

                    result = flash_image(
                        img.name,
                        "/dev/sdb",
                        dry_run=True,
                    )

                    assert isinstance(result, FlashResult)
                    assert result.success is True
                    assert "dry-run" in result.message.lower()
                    assert result.flash_record_id is None
            finally:
                os.unlink(img.name)

    def test_device_validation_failure_returns_result(self):
        """Device validation failure returns error result."""
        from openwrt_imagegen.flash.device import DeviceNotFoundError

        with tempfile.NamedTemporaryFile(delete=False, suffix=".img") as img:
            img.write(b"Content")
            img.flush()

            try:
                with patch(
                    "openwrt_imagegen.flash.service.validate_device",
                    side_effect=DeviceNotFoundError("/dev/nonexistent"),
                ):
                    result = flash_image(
                        img.name,
                        "/dev/nonexistent",
                    )

                    assert result.success is False
                    assert result.error_code == "DEVICE_NOT_FOUND"
                    assert "not found" in result.error_message.lower()
            finally:
                os.unlink(img.name)

    def test_successful_flash(self):
        """Test successful flash operation."""
        image_content = b"Test image content"

        with tempfile.NamedTemporaryFile(delete=False, suffix=".img") as img:
            img.write(image_content)
            img.flush()

            with tempfile.NamedTemporaryFile(delete=False, suffix=".dev") as dev:
                dev.write(b"\x00" * 100)
                dev.flush()

                try:
                    with patch(
                        "openwrt_imagegen.flash.service.validate_device"
                    ) as mock_validate:
                        mock_validate.return_value = MagicMock(
                            path=dev.name,
                            is_block_device=True,
                            is_whole_device=True,
                            is_mounted=False,
                            mount_points=[],
                            size_bytes=100,
                            model=None,
                            serial=None,
                        )

                        result = flash_image(
                            img.name,
                            dev.name,
                            verification_mode=VerificationMode.FULL,
                        )

                        assert result.success is True
                        assert result.bytes_written == len(image_content)
                        assert result.verification_result == VerificationResult.MATCH
                        assert result.flash_record_id is None  # No session
                finally:
                    os.unlink(img.name)
                    os.unlink(dev.name)


class TestFlashArtifact:
    """Tests for flash_artifact function."""

    def test_artifact_not_found(self):
        """Raise error when artifact doesn't exist."""
        session = MagicMock()
        session.get.return_value = None

        with pytest.raises(ArtifactNotFoundError) as exc_info:
            flash_artifact(session, artifact_id=999, device_path="/dev/sdb")

        assert exc_info.value.artifact_id == 999
        assert exc_info.value.error_code == "ARTIFACT_NOT_FOUND"

    def test_artifact_file_not_found(self):
        """Raise error when artifact file doesn't exist on disk."""
        session = MagicMock()

        # Mock artifact with non-existent path
        mock_artifact = MagicMock()
        mock_artifact.id = 1
        mock_artifact.build_id = 1
        mock_artifact.absolute_path = "/nonexistent/path/image.img"
        session.get.return_value = mock_artifact

        with pytest.raises(ArtifactFileNotFoundError) as exc_info:
            flash_artifact(session, artifact_id=1, device_path="/dev/sdb")

        assert exc_info.value.artifact_id == 1
        assert exc_info.value.error_code == "ARTIFACT_FILE_NOT_FOUND"

    def test_flash_artifact_dry_run(self):
        """Dry run flash artifact operation."""
        session = MagicMock()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".img") as img:
            img.write(b"Test content")
            img.flush()

            try:
                # Mock artifact
                mock_artifact = MagicMock()
                mock_artifact.id = 1
                mock_artifact.build_id = 1
                mock_artifact.absolute_path = img.name
                session.get.return_value = mock_artifact

                with patch(
                    "openwrt_imagegen.flash.service.validate_device"
                ) as mock_validate:
                    mock_validate.return_value = MagicMock(
                        path="/dev/sdb",
                        is_block_device=True,
                        is_whole_device=True,
                        is_mounted=False,
                        mount_points=[],
                        size_bytes=1000000,
                        model=None,
                        serial=None,
                    )

                    result = flash_artifact(
                        session,
                        artifact_id=1,
                        device_path="/dev/sdb",
                        dry_run=True,
                    )

                    assert result.success is True
                    assert "dry-run" in result.message.lower()
            finally:
                os.unlink(img.name)


class TestGetFlashRecords:
    """Tests for get_flash_records function."""

    def test_query_with_filters(self):
        """Query flash records with various filters."""
        # Create mock session with execute that returns scalars
        session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result

        # Should not raise
        records = get_flash_records(
            session,
            artifact_id=1,
            build_id=2,
            device_path="/dev/sdb",
            status=FlashStatus.SUCCEEDED,
            limit=50,
        )

        assert records == []
        session.execute.assert_called_once()

    def test_query_no_filters(self):
        """Query all flash records."""
        session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result

        records = get_flash_records(session)

        assert records == []


class TestFlashResult:
    """Tests for FlashResult dataclass."""

    def test_success_result(self):
        """Create successful flash result."""
        result = FlashResult(
            success=True,
            flash_record_id=42,
            image_path="/path/to/image.img",
            device_path="/dev/sdb",
            bytes_written=1024,
            source_hash="abc123",
            device_hash="abc123",
            verification_mode=VerificationMode.FULL,
            verification_result=VerificationResult.MATCH,
        )

        assert result.success is True
        assert result.flash_record_id == 42
        assert result.bytes_written == 1024
        assert result.error_message is None
        assert result.error_code is None

    def test_failure_result(self):
        """Create failed flash result."""
        result = FlashResult(
            success=False,
            flash_record_id=None,
            image_path="/path/to/image.img",
            device_path="/dev/sdb",
            bytes_written=0,
            source_hash="abc123",
            device_hash=None,
            verification_mode=VerificationMode.FULL,
            verification_result=VerificationResult.SKIPPED,
            error_message="Device not found",
            error_code="DEVICE_NOT_FOUND",
        )

        assert result.success is False
        assert result.error_message == "Device not found"
        assert result.error_code == "DEVICE_NOT_FOUND"


class TestFlashPlan:
    """Tests for FlashPlan dataclass."""

    def test_plan_dataclass(self):
        """Create FlashPlan with all fields."""
        device_info = MagicMock(
            path="/dev/sdb",
            is_block_device=True,
            is_whole_device=True,
            is_mounted=False,
            mount_points=[],
            size_bytes=4000000000,
        )

        plan = FlashPlan(
            image_path="/path/to/image.img",
            image_size=1024,
            image_hash="abc123",
            device_path="/dev/sdb",
            device_info=device_info,
            wipe_before=True,
            verification_mode=VerificationMode.PREFIX_16M,
            artifact_id=1,
            build_id=2,
        )

        assert plan.image_path == "/path/to/image.img"
        assert plan.image_size == 1024
        assert plan.wipe_before is True
        assert plan.artifact_id == 1
        assert plan.build_id == 2
