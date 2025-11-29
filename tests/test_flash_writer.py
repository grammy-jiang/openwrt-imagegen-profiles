"""Tests for flash/writer.py - write operations and hash verification."""

import hashlib
import os
import tempfile
from unittest.mock import patch

import pytest

from openwrt_imagegen.flash.writer import (
    DEFAULT_BLOCK_SIZE,
    HashMismatchError,
    ImageNotFoundError,
    WriteResult,
    compute_device_hash,
    compute_file_hash,
    verify_device_hash,
    wipe_device,
    write_image_to_device,
)
from openwrt_imagegen.types import VerificationMode, VerificationResult


class TestComputeFileHash:
    """Tests for compute_file_hash function."""

    def test_empty_file(self):
        """Hash of empty file."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"")
            f.flush()
            try:
                hash_result, bytes_hashed = compute_file_hash(f.name)
                # SHA-256 of empty string
                expected = hashlib.sha256(b"").hexdigest()
                assert hash_result == expected
                assert bytes_hashed == 0
            finally:
                os.unlink(f.name)

    def test_small_file(self):
        """Hash of small file."""
        content = b"Hello, World!"
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(content)
            f.flush()
            try:
                hash_result, bytes_hashed = compute_file_hash(f.name)
                expected = hashlib.sha256(content).hexdigest()
                assert hash_result == expected
                assert bytes_hashed == len(content)
            finally:
                os.unlink(f.name)

    def test_large_file(self):
        """Hash of file larger than block size."""
        # Create file larger than default block size
        content = os.urandom(DEFAULT_BLOCK_SIZE + 1000)
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(content)
            f.flush()
            try:
                hash_result, bytes_hashed = compute_file_hash(f.name)
                expected = hashlib.sha256(content).hexdigest()
                assert hash_result == expected
                assert bytes_hashed == len(content)
            finally:
                os.unlink(f.name)

    def test_prefix_hash(self):
        """Hash only a prefix of the file."""
        content = b"ABCDEFGHIJ"  # 10 bytes
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(content)
            f.flush()
            try:
                hash_result, bytes_hashed = compute_file_hash(f.name, max_bytes=5)
                expected = hashlib.sha256(b"ABCDE").hexdigest()
                assert hash_result == expected
                assert bytes_hashed == 5
            finally:
                os.unlink(f.name)

    def test_prefix_larger_than_file(self):
        """Prefix larger than file should hash entire file."""
        content = b"SHORT"
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(content)
            f.flush()
            try:
                hash_result, bytes_hashed = compute_file_hash(f.name, max_bytes=1000)
                expected = hashlib.sha256(content).hexdigest()
                assert hash_result == expected
                assert bytes_hashed == len(content)
            finally:
                os.unlink(f.name)


class TestComputeDeviceHash:
    """Tests for compute_device_hash function."""

    def test_hash_from_file(self):
        """Read hash from a regular file (simulating device)."""
        content = b"Device content here"
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(content)
            f.flush()
            try:
                hash_result = compute_device_hash(f.name, len(content))
                expected = hashlib.sha256(content).hexdigest()
                assert hash_result == expected
            finally:
                os.unlink(f.name)

    def test_partial_read(self):
        """Read only part of the file."""
        content = b"0123456789"
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(content)
            f.flush()
            try:
                hash_result = compute_device_hash(f.name, 5)
                expected = hashlib.sha256(b"01234").hexdigest()
                assert hash_result == expected
            finally:
                os.unlink(f.name)


class TestVerifyDeviceHash:
    """Tests for verify_device_hash function."""

    def test_hash_match(self):
        """Verify matching hash."""
        content = b"Test content"
        expected_hash = hashlib.sha256(content).hexdigest()

        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(content)
            f.flush()
            try:
                matches, actual = verify_device_hash(
                    f.name, expected_hash, len(content)
                )
                assert matches is True
                assert actual == expected_hash
            finally:
                os.unlink(f.name)

    def test_hash_mismatch(self):
        """Verify mismatching hash."""
        content = b"Test content"
        wrong_hash = hashlib.sha256(b"Different content").hexdigest()

        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(content)
            f.flush()
            try:
                matches, actual = verify_device_hash(f.name, wrong_hash, len(content))
                assert matches is False
                assert actual == hashlib.sha256(content).hexdigest()
            finally:
                os.unlink(f.name)


class TestWipeDevice:
    """Tests for wipe_device function."""

    def test_wipe_beginning(self):
        """Wipe beginning of a file (simulating device)."""
        original = b"AAAA" + b"BBBB" * 100
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(original)
            f.flush()
            try:
                bytes_wiped = wipe_device(f.name, wipe_bytes=4)
                assert bytes_wiped == 4

                # Read back and verify
                with open(f.name, "rb") as rf:
                    data = rf.read()
                    assert data[:4] == b"\x00\x00\x00\x00"
                    assert data[4:8] == b"BBBB"  # Rest unchanged
            finally:
                os.unlink(f.name)

    def test_wipe_larger_than_file(self):
        """Wipe more bytes than file contains."""
        original = b"AAAA"
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(original)
            f.flush()
            try:
                # Wipe 8 bytes but file is only 4
                bytes_wiped = wipe_device(f.name, wipe_bytes=8)
                # Should still report 8 (fills with zeros beyond file)
                assert bytes_wiped == 8

                with open(f.name, "rb") as rf:
                    data = rf.read()
                    assert data == b"\x00" * 8
            finally:
                os.unlink(f.name)


class TestWriteImageToDevice:
    """Tests for write_image_to_device function."""

    def test_write_success_with_verification(self):
        """Write image and verify hash matches."""
        image_content = os.urandom(1024)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".img") as img:
            img.write(image_content)
            img.flush()

            with tempfile.NamedTemporaryFile(delete=False, suffix=".dev") as dev:
                # Pre-fill device with zeros
                dev.write(b"\x00" * 2048)
                dev.flush()

                try:
                    result = write_image_to_device(
                        img.name,
                        dev.name,
                        verification_mode=VerificationMode.FULL,
                    )

                    assert result.success is True
                    assert result.bytes_written == 1024
                    assert result.verification_result == VerificationResult.MATCH
                    assert result.source_hash is not None
                    assert result.device_hash is not None
                    assert result.source_hash == result.device_hash

                    # Verify file content
                    with open(dev.name, "rb") as f:
                        data = f.read(1024)
                        assert data == image_content
                finally:
                    os.unlink(img.name)
                    os.unlink(dev.name)

    def test_write_success_skip_verification(self):
        """Write image without verification."""
        image_content = b"Test image"

        with tempfile.NamedTemporaryFile(delete=False, suffix=".img") as img:
            img.write(image_content)
            img.flush()

            with tempfile.NamedTemporaryFile(delete=False, suffix=".dev") as dev:
                dev.write(b"\x00" * 100)
                dev.flush()

                try:
                    result = write_image_to_device(
                        img.name,
                        dev.name,
                        verification_mode=VerificationMode.SKIP,
                    )

                    assert result.success is True
                    assert result.bytes_written == len(image_content)
                    assert result.verification_result == VerificationResult.SKIPPED
                    assert result.device_hash is None
                finally:
                    os.unlink(img.name)
                    os.unlink(dev.name)

    def test_write_with_wipe(self):
        """Write image with wipe before."""
        image_content = b"NEW IMAGE"
        old_content = b"OLD DATA HERE"

        with tempfile.NamedTemporaryFile(delete=False, suffix=".img") as img:
            img.write(image_content)
            img.flush()

            with tempfile.NamedTemporaryFile(delete=False, suffix=".dev") as dev:
                dev.write(old_content + b"\x00" * 100)
                dev.flush()

                try:
                    result = write_image_to_device(
                        img.name,
                        dev.name,
                        wipe_before=True,
                        verification_mode=VerificationMode.FULL,
                    )

                    assert result.success is True
                    assert result.bytes_written == len(image_content)
                finally:
                    os.unlink(img.name)
                    os.unlink(dev.name)

    def test_write_image_not_found(self):
        """Raise error for missing image file."""
        with pytest.raises(ImageNotFoundError) as exc_info:
            write_image_to_device(
                "/nonexistent/image.img",
                "/dev/null",
            )

        assert "not found" in str(exc_info.value).lower()
        assert exc_info.value.error_code == "IMAGE_NOT_FOUND"

    def test_write_prefix_verification(self):
        """Write with prefix verification mode."""
        # Create image larger than 16MiB prefix
        image_size = 20 * 1024 * 1024  # 20 MiB
        image_content = os.urandom(image_size)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".img") as img:
            img.write(image_content)
            img.flush()

            with tempfile.NamedTemporaryFile(delete=False, suffix=".dev") as dev:
                dev.write(b"\x00" * (image_size + 1024))
                dev.flush()

                try:
                    result = write_image_to_device(
                        img.name,
                        dev.name,
                        verification_mode=VerificationMode.PREFIX_16M,
                    )

                    assert result.success is True
                    assert result.bytes_written == image_size
                    assert result.verification_result == VerificationResult.MATCH
                    assert result.verification_mode == VerificationMode.PREFIX_16M
                finally:
                    os.unlink(img.name)
                    os.unlink(dev.name)

    def test_hash_mismatch_detection(self):
        """Detect hash mismatch after write."""
        image_content = b"Test image content"

        with tempfile.NamedTemporaryFile(delete=False, suffix=".img") as img:
            img.write(image_content)
            img.flush()

            with tempfile.NamedTemporaryFile(delete=False, suffix=".dev") as dev:
                dev.write(b"\x00" * 100)
                dev.flush()

                try:
                    # Mock compute_device_hash to return wrong hash
                    with patch(
                        "openwrt_imagegen.flash.writer.compute_device_hash"
                    ) as mock_hash:
                        mock_hash.return_value = "0" * 64  # Wrong hash

                        with pytest.raises(HashMismatchError) as exc_info:
                            write_image_to_device(
                                img.name,
                                dev.name,
                                verification_mode=VerificationMode.FULL,
                            )

                        assert "verification failed" in str(exc_info.value).lower()
                        assert exc_info.value.error_code == "HASH_MISMATCH"
                finally:
                    os.unlink(img.name)
                    os.unlink(dev.name)

    def test_write_with_provided_hash(self):
        """Write using a pre-computed hash."""
        image_content = b"Test content"
        expected_hash = hashlib.sha256(image_content).hexdigest()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".img") as img:
            img.write(image_content)
            img.flush()

            with tempfile.NamedTemporaryFile(delete=False, suffix=".dev") as dev:
                dev.write(b"\x00" * 100)
                dev.flush()

                try:
                    result = write_image_to_device(
                        img.name,
                        dev.name,
                        verification_mode=VerificationMode.FULL,
                        expected_hash=expected_hash,
                    )

                    assert result.success is True
                    assert result.source_hash == expected_hash
                    assert result.verification_result == VerificationResult.MATCH
                finally:
                    os.unlink(img.name)
                    os.unlink(dev.name)


class TestWriteResult:
    """Tests for WriteResult dataclass."""

    def test_success_result(self):
        """Create successful write result."""
        result = WriteResult(
            success=True,
            bytes_written=1024,
            source_hash="abc123",
            device_hash="abc123",
            verification_mode=VerificationMode.FULL,
            verification_result=VerificationResult.MATCH,
        )
        assert result.success is True
        assert result.bytes_written == 1024
        assert result.error_message is None

    def test_failure_result(self):
        """Create failed write result."""
        result = WriteResult(
            success=False,
            bytes_written=0,
            source_hash="abc123",
            device_hash="def456",
            verification_mode=VerificationMode.FULL,
            verification_result=VerificationResult.MISMATCH,
            error_message="Hash mismatch",
        )
        assert result.success is False
        assert result.error_message == "Hash mismatch"
