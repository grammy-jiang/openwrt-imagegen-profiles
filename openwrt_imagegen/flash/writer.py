"""Writer module for TF/SD card flashing.

This module handles the actual write operations:
- Write image to device with fsync
- Hash verification (full and prefix modes)
- Optional wipe functionality

All operations follow the safety rules in docs/SAFETY.md:
- Synchronous, flushed writes (conv=fsync equivalent)
- Hash-based verification after write
- Detailed logging of operations
"""

import hashlib
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from openwrt_imagegen.types import VerificationMode, VerificationResult

logger = logging.getLogger(__name__)

# Default block size for I/O operations (1 MiB)
DEFAULT_BLOCK_SIZE = 1024 * 1024

# Size prefixes for verification modes
VERIFICATION_SIZE_BYTES = {
    VerificationMode.PREFIX_16M: 16 * 1024 * 1024,
    VerificationMode.PREFIX_64M: 64 * 1024 * 1024,
}


@dataclass
class WriteResult:
    """Result of a write operation.

    Attributes:
        success: Whether the write succeeded.
        bytes_written: Number of bytes written.
        source_hash: SHA-256 hash of the source image (or prefix).
        device_hash: SHA-256 hash read back from device (or prefix).
        verification_mode: Verification mode used.
        verification_result: Result of hash verification.
        error_message: Error message if write failed.
    """

    success: bool
    bytes_written: int
    source_hash: str
    device_hash: str | None
    verification_mode: VerificationMode
    verification_result: VerificationResult
    error_message: str | None = None


class WriteError(Exception):
    """Error during write operation."""

    def __init__(self, message: str, error_code: str) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code


class ImageNotFoundError(WriteError):
    """Image file does not exist."""

    def __init__(self, image_path: str) -> None:
        super().__init__(
            f"Image file not found: {image_path}", error_code="IMAGE_NOT_FOUND"
        )
        self.image_path = image_path


class WritePermissionError(WriteError):
    """Permission denied when writing to device."""

    def __init__(self, device_path: str) -> None:
        super().__init__(
            f"Permission denied writing to device: {device_path}. "
            "Try running with elevated privileges.",
            error_code="WRITE_PERMISSION_DENIED",
        )
        self.device_path = device_path


class WriteIOError(WriteError):
    """I/O error during write operation."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="WRITE_IO_ERROR")


class HashMismatchError(WriteError):
    """Hash verification failed after write."""

    def __init__(
        self, device_path: str, expected_hash: str, actual_hash: str, mode: str
    ) -> None:
        super().__init__(
            f"Hash verification failed for {device_path}. "
            f"Expected: {expected_hash[:16]}..., Got: {actual_hash[:16]}... "
            f"(mode: {mode}). The card may be defective or a ghost write occurred.",
            error_code="HASH_MISMATCH",
        )
        self.device_path = device_path
        self.expected_hash = expected_hash
        self.actual_hash = actual_hash
        self.mode = mode


def compute_file_hash(
    file_path: str | Path,
    max_bytes: int | None = None,
    block_size: int = DEFAULT_BLOCK_SIZE,
) -> tuple[str, int]:
    """Compute SHA-256 hash of a file.

    Args:
        file_path: Path to the file to hash.
        max_bytes: Maximum number of bytes to hash (for prefix verification).
        block_size: Block size for reading.

    Returns:
        Tuple of (hex hash string, bytes hashed).
    """
    hasher = hashlib.sha256()
    bytes_hashed = 0

    with open(file_path, "rb") as f:
        while True:
            # Calculate how much to read
            if max_bytes is not None:
                remaining = max_bytes - bytes_hashed
                if remaining <= 0:
                    break
                read_size = min(block_size, remaining)
            else:
                read_size = block_size

            chunk = f.read(read_size)
            if not chunk:
                break

            hasher.update(chunk)
            bytes_hashed += len(chunk)

    return hasher.hexdigest(), bytes_hashed


def compute_device_hash(
    device_path: str,
    num_bytes: int,
    block_size: int = DEFAULT_BLOCK_SIZE,
) -> str:
    """Compute SHA-256 hash of data read from a device.

    Args:
        device_path: Path to the device to read.
        num_bytes: Number of bytes to read and hash.
        block_size: Block size for reading.

    Returns:
        Hex hash string.
    """
    hasher = hashlib.sha256()
    bytes_read = 0

    with open(device_path, "rb") as f:
        while bytes_read < num_bytes:
            remaining = num_bytes - bytes_read
            read_size = min(block_size, remaining)
            chunk = f.read(read_size)
            if not chunk:
                break
            hasher.update(chunk)
            bytes_read += len(chunk)

    return hasher.hexdigest()


def _write_with_progress(
    source: BinaryIO,
    dest: BinaryIO,
    total_bytes: int,
    block_size: int = DEFAULT_BLOCK_SIZE,
) -> int:
    """Write data from source to destination with progress tracking.

    Args:
        source: Source file object.
        dest: Destination file object.
        total_bytes: Total bytes to write.
        block_size: Block size for I/O.

    Returns:
        Number of bytes written.
    """
    bytes_written = 0

    while bytes_written < total_bytes:
        chunk = source.read(block_size)
        if not chunk:
            break

        dest.write(chunk)
        bytes_written += len(chunk)

        # Log progress every 10 MiB
        if bytes_written % (10 * 1024 * 1024) < block_size:
            progress = (bytes_written / total_bytes) * 100
            logger.debug(
                "Write progress: %d / %d bytes (%.1f%%)",
                bytes_written,
                total_bytes,
                progress,
            )

    return bytes_written


def wipe_device(
    device_path: str,
    wipe_bytes: int = 1024 * 1024,
    block_size: int = DEFAULT_BLOCK_SIZE,
) -> int:
    """Wipe the beginning of a device with zeros.

    This clears filesystem/partition signatures to avoid confusion
    with previous contents.

    Args:
        device_path: Path to the device.
        wipe_bytes: Number of bytes to zero (default 1 MiB).
        block_size: Block size for writing.

    Returns:
        Number of bytes wiped.

    Raises:
        WritePermissionError: Permission denied.
        WriteIOError: I/O error during wipe.
    """
    logger.info("Wiping first %d bytes of %s", wipe_bytes, device_path)

    try:
        with open(device_path, "r+b") as f:
            bytes_wiped = 0
            zeros = b"\x00" * block_size

            while bytes_wiped < wipe_bytes:
                remaining = wipe_bytes - bytes_wiped
                write_size = min(block_size, remaining)
                f.write(zeros[:write_size])
                bytes_wiped += write_size

            # Flush to device
            f.flush()
            os.fsync(f.fileno())

        logger.info("Wiped %d bytes", bytes_wiped)
        return bytes_wiped

    except PermissionError as e:
        logger.error("Permission denied wiping device: %s", e)
        raise WritePermissionError(device_path) from e
    except OSError as e:
        logger.error("I/O error wiping device: %s", e)
        raise WriteIOError(f"Error wiping device {device_path}: {e}") from e


def write_image_to_device(
    image_path: str | Path,
    device_path: str,
    *,
    wipe_before: bool = False,
    verification_mode: VerificationMode = VerificationMode.FULL,
    block_size: int = DEFAULT_BLOCK_SIZE,
    expected_hash: str | None = None,
) -> WriteResult:
    """Write an image file to a block device with verification.

    This is the core write function that:
    1. Optionally wipes the device first
    2. Writes the image with fsync
    3. Verifies the write by reading back and comparing hashes

    Args:
        image_path: Path to the image file.
        device_path: Path to the target device.
        wipe_before: Whether to wipe device before writing.
        verification_mode: How to verify the write.
        block_size: Block size for I/O operations.
        expected_hash: Pre-computed hash of the image (optional).

    Returns:
        WriteResult with operation details.

    Raises:
        ImageNotFoundError: Image file not found.
        WritePermissionError: Permission denied.
        WriteIOError: I/O error during write.
        HashMismatchError: Verification failed.
    """
    image_path = Path(image_path)

    # Validate image exists
    if not image_path.exists():
        raise ImageNotFoundError(str(image_path))

    image_size = image_path.stat().st_size
    logger.info(
        "Writing image %s (%d bytes) to %s",
        image_path.name,
        image_size,
        device_path,
    )

    # Determine verification size
    if verification_mode == VerificationMode.SKIP:
        verify_bytes = 0
    elif verification_mode in VERIFICATION_SIZE_BYTES:
        # Use prefix size, but not more than image size
        verify_bytes = min(VERIFICATION_SIZE_BYTES[verification_mode], image_size)
    else:
        # Full verification
        verify_bytes = image_size

    # Compute source hash (if not provided)
    if expected_hash is None and verification_mode != VerificationMode.SKIP:
        logger.debug(
            "Computing source hash (mode=%s, bytes=%d)", verification_mode, verify_bytes
        )
        source_hash, _ = compute_file_hash(
            image_path, max_bytes=verify_bytes if verify_bytes < image_size else None
        )
    elif expected_hash is not None:
        source_hash = expected_hash
    else:
        source_hash = ""

    logger.debug("Source hash: %s", source_hash[:16] if source_hash else "N/A")

    # Wipe if requested
    if wipe_before:
        wipe_device(device_path, block_size=block_size)

    # Write image to device
    bytes_written = 0
    try:
        with open(image_path, "rb") as src, open(device_path, "r+b") as dst:
            bytes_written = _write_with_progress(
                src, dst, image_size, block_size=block_size
            )

            # Flush all buffers and sync to device
            dst.flush()
            os.fsync(dst.fileno())

        logger.info("Wrote %d bytes to %s", bytes_written, device_path)

    except PermissionError as e:
        logger.error("Permission denied writing to device: %s", e)
        raise WritePermissionError(device_path) from e
    except OSError as e:
        logger.error("I/O error writing to device: %s", e)
        raise WriteIOError(f"Error writing to {device_path}: {e}") from e

    # Call sync to ensure all writes are flushed
    os.sync()

    # Verify write
    verification_result = VerificationResult.SKIPPED
    device_hash: str | None = None

    if verification_mode != VerificationMode.SKIP:
        logger.info(
            "Verifying write (mode=%s, bytes=%d)", verification_mode, verify_bytes
        )

        device_hash = compute_device_hash(
            device_path, verify_bytes, block_size=block_size
        )
        logger.debug("Device hash: %s", device_hash[:16])

        if device_hash == source_hash:
            verification_result = VerificationResult.MATCH
            logger.info("Hash verification passed")
        else:
            verification_result = VerificationResult.MISMATCH
            logger.error(
                "Hash verification FAILED: expected=%s, got=%s",
                source_hash[:16],
                device_hash[:16],
            )
            raise HashMismatchError(
                device_path,
                source_hash,
                device_hash,
                verification_mode.value,
            )

    return WriteResult(
        success=True,
        bytes_written=bytes_written,
        source_hash=source_hash,
        device_hash=device_hash,
        verification_mode=verification_mode,
        verification_result=verification_result,
    )


def verify_device_hash(
    device_path: str,
    expected_hash: str,
    num_bytes: int,
    block_size: int = DEFAULT_BLOCK_SIZE,
) -> tuple[bool, str]:
    """Verify that a device contains expected data by comparing hashes.

    This can be used to verify a device without writing, e.g., to check
    if a previously flashed card still has the correct content.

    Args:
        device_path: Path to the device.
        expected_hash: Expected SHA-256 hash.
        num_bytes: Number of bytes to verify.
        block_size: Block size for reading.

    Returns:
        Tuple of (match: bool, actual_hash: str).
    """
    logger.info(
        "Verifying %d bytes of %s against hash %s...",
        num_bytes,
        device_path,
        expected_hash[:16],
    )

    actual_hash = compute_device_hash(device_path, num_bytes, block_size)

    matches = actual_hash == expected_hash
    if matches:
        logger.info("Hash verification passed")
    else:
        logger.warning(
            "Hash mismatch: expected=%s, got=%s", expected_hash[:16], actual_hash[:16]
        )

    return matches, actual_hash


__all__ = [
    "DEFAULT_BLOCK_SIZE",
    "HashMismatchError",
    "ImageNotFoundError",
    "WriteError",
    "WriteIOError",
    "WritePermissionError",
    "WriteResult",
    "compute_device_hash",
    "compute_file_hash",
    "verify_device_hash",
    "wipe_device",
    "write_image_to_device",
]
