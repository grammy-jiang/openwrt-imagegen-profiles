"""Device validation for TF/SD card flashing.

This module handles all device-related validation before flashing:
- Validate device path exists and is a block device
- Ensure whole-device only (reject partitions like /dev/sda1)
- Check device is not a system root device (optional safety check)
- Check mount status and warn/refuse if mounted

All operations follow the safety rules in docs/SAFETY.md:
- Explicit device paths only (no guessing)
- No auto-selection of devices
"""

import logging
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class DeviceInfo:
    """Information about a validated block device.

    Attributes:
        path: Absolute path to the device (e.g., '/dev/sda').
        is_block_device: Whether the path is a block device.
        is_whole_device: Whether this is a whole device (not a partition).
        is_mounted: Whether any partitions on this device are mounted.
        mount_points: List of mount points if device is mounted.
        size_bytes: Size of the device in bytes (if available).
        model: Device model string (if available).
        serial: Device serial number (if available).
    """

    path: str
    is_block_device: bool
    is_whole_device: bool
    is_mounted: bool
    mount_points: list[str]
    size_bytes: int | None = None
    model: str | None = None
    serial: str | None = None


class DeviceValidationError(Exception):
    """Base exception for device validation errors."""

    def __init__(self, message: str, error_code: str) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code


class DeviceNotFoundError(DeviceValidationError):
    """Device path does not exist."""

    def __init__(self, device_path: str) -> None:
        super().__init__(
            f"Device not found: {device_path}", error_code="DEVICE_NOT_FOUND"
        )
        self.device_path = device_path


class NotBlockDeviceError(DeviceValidationError):
    """Path exists but is not a block device."""

    def __init__(self, device_path: str) -> None:
        super().__init__(
            f"Not a block device: {device_path}", error_code="NOT_BLOCK_DEVICE"
        )
        self.device_path = device_path


class PartitionDeviceError(DeviceValidationError):
    """Device appears to be a partition, not a whole device."""

    def __init__(self, device_path: str) -> None:
        super().__init__(
            f"Device appears to be a partition, not a whole device: {device_path}. "
            "Only whole devices (e.g., /dev/sda, /dev/mmcblk0) are supported.",
            error_code="PARTITION_NOT_ALLOWED",
        )
        self.device_path = device_path


class DeviceMountedError(DeviceValidationError):
    """Device or its partitions are mounted."""

    def __init__(self, device_path: str, mount_points: list[str]) -> None:
        mounts_str = ", ".join(mount_points)
        super().__init__(
            f"Device {device_path} has mounted partitions: {mounts_str}. "
            "Unmount all partitions before flashing.",
            error_code="DEVICE_MOUNTED",
        )
        self.device_path = device_path
        self.mount_points = mount_points


class SystemDeviceError(DeviceValidationError):
    """Device appears to be the system root device."""

    def __init__(self, device_path: str) -> None:
        super().__init__(
            f"Device {device_path} appears to be the system root device. "
            "Refusing to flash to avoid data loss.",
            error_code="SYSTEM_DEVICE",
        )
        self.device_path = device_path


# Patterns for partition detection
# /dev/sdX1, /dev/hdX1, /dev/vdX1
_PARTITION_PATTERN_SD = re.compile(r"^/dev/[shv]d[a-z]+(\d+)$")
# /dev/nvme0n1p1, /dev/nvme0n1p2
_PARTITION_PATTERN_NVME = re.compile(r"^/dev/nvme\d+n\d+p(\d+)$")
# /dev/mmcblk0p1, /dev/mmcblk0p2
_PARTITION_PATTERN_MMC = re.compile(r"^/dev/mmcblk\d+p(\d+)$")
# /dev/loop0p1
_PARTITION_PATTERN_LOOP = re.compile(r"^/dev/loop\d+p(\d+)$")


def is_partition_path(device_path: str) -> bool:
    """Check if a device path looks like a partition.

    This uses naming conventions to detect partitions:
    - /dev/sda1, /dev/sdb2 (SCSI/SATA/USB)
    - /dev/mmcblk0p1, /dev/mmcblk0p2 (MMC/SD cards)
    - /dev/nvme0n1p1 (NVMe)
    - /dev/loop0p1 (Loop devices with partitions)

    Args:
        device_path: Path to the device.

    Returns:
        True if the path appears to be a partition, False otherwise.
    """
    patterns = [
        _PARTITION_PATTERN_SD,
        _PARTITION_PATTERN_NVME,
        _PARTITION_PATTERN_MMC,
        _PARTITION_PATTERN_LOOP,
    ]

    return any(pattern.match(device_path) for pattern in patterns)


def is_block_device(device_path: str) -> bool:
    """Check if a path is a block device.

    Args:
        device_path: Path to check.

    Returns:
        True if the path is a block device, False otherwise.
    """
    try:
        mode = os.stat(device_path).st_mode
        return stat.S_ISBLK(mode)
    except OSError:
        return False


def get_mount_points(device_path: str) -> list[str]:
    """Get mount points for a device and its partitions.

    Parses /proc/mounts to find any mounted partitions associated
    with the given device.

    Args:
        device_path: Path to the device (e.g., '/dev/sda').

    Returns:
        List of mount points (empty if none mounted).
    """
    mount_points: list[str] = []
    device_name = Path(device_path).name

    try:
        with open("/proc/mounts") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    mounted_device = parts[0]
                    mount_point = parts[1]

                    # Check if this is the device or one of its partitions
                    # Must be exact match or device name followed by a digit (partition)
                    mounted_name = Path(mounted_device).name
                    if mounted_name == device_name:
                        mount_points.append(mount_point)
                    elif (
                        mounted_name.startswith(device_name)
                        and len(mounted_name) > len(device_name)
                        and (
                            mounted_name[len(device_name)].isdigit()
                            or mounted_name[len(device_name)] == "p"
                        )
                    ):
                        # Matches partitions like sda1, sda2 or mmcblk0p1, nvme0n1p1
                        mount_points.append(mount_point)
    except OSError:
        # If we can't read /proc/mounts, assume nothing is mounted
        logger.warning("Could not read /proc/mounts, skipping mount check")

    return mount_points


def get_root_device() -> str | None:
    """Get the device that contains the root filesystem.

    Reads /proc/mounts to find the device mounted at '/'.

    Returns:
        Path to the root device (whole device, not partition), or None if unknown.
    """
    try:
        with open("/proc/mounts") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2 and parts[1] == "/":
                    root_partition = parts[0]
                    # Convert partition to whole device
                    return _partition_to_whole_device(root_partition)
    except OSError:
        logger.warning("Could not read /proc/mounts to determine root device")

    return None


def _partition_to_whole_device(partition_path: str) -> str:
    """Convert a partition path to its whole device path.

    Args:
        partition_path: Path to a partition (e.g., '/dev/sda1').

    Returns:
        Path to the whole device (e.g., '/dev/sda').
    """
    # Handle /dev/sdXN -> /dev/sdX
    match = _PARTITION_PATTERN_SD.match(partition_path)
    if match:
        return partition_path[: -len(match.group(1))]

    # Handle /dev/nvme0n1pN -> /dev/nvme0n1
    match = _PARTITION_PATTERN_NVME.match(partition_path)
    if match:
        return partition_path[: partition_path.rfind("p")]

    # Handle /dev/mmcblk0pN -> /dev/mmcblk0
    match = _PARTITION_PATTERN_MMC.match(partition_path)
    if match:
        return partition_path[: partition_path.rfind("p")]

    # Handle /dev/loop0pN -> /dev/loop0
    match = _PARTITION_PATTERN_LOOP.match(partition_path)
    if match:
        return partition_path[: partition_path.rfind("p")]

    # If no pattern matches, return as-is (might already be whole device)
    return partition_path


def get_device_size(device_path: str) -> int | None:
    """Get the size of a block device in bytes.

    Uses the sysfs interface to read device size.

    Args:
        device_path: Path to the device.

    Returns:
        Size in bytes, or None if unknown.
    """
    device_name = Path(device_path).name
    size_path = Path(f"/sys/block/{device_name}/size")

    try:
        if size_path.exists():
            # Size is in 512-byte sectors
            sectors = int(size_path.read_text().strip())
            return sectors * 512
    except (OSError, ValueError) as e:
        logger.warning(f"Could not read device size for {device_path}: {e}")

    return None


def validate_device(
    device_path: str,
    *,
    check_mount: bool = True,
    check_system_device: bool = True,
    allow_mounted: bool = False,
) -> DeviceInfo:
    """Validate a device path for flashing.

    Performs comprehensive validation of a device path before allowing
    flash operations:
    1. Check that the path exists
    2. Check that it is a block device
    3. Check that it is a whole device (not a partition)
    4. Optionally check that it is not the system root device
    5. Optionally check that it is not mounted

    Args:
        device_path: Path to the device to validate.
        check_mount: Whether to check if device is mounted.
        check_system_device: Whether to refuse the system root device.
        allow_mounted: If True, warn about mounted devices but don't raise.

    Returns:
        DeviceInfo with validation results.

    Raises:
        DeviceNotFoundError: Device path does not exist.
        NotBlockDeviceError: Path is not a block device.
        PartitionDeviceError: Device is a partition, not whole device.
        SystemDeviceError: Device is the system root device.
        DeviceMountedError: Device is mounted and allow_mounted is False.
    """
    # Normalize path
    device_path = os.path.abspath(device_path)

    logger.debug("Validating device: %s", device_path)

    # Check existence
    if not os.path.exists(device_path):
        logger.error("Device not found: %s", device_path)
        raise DeviceNotFoundError(device_path)

    # Check if block device
    if not is_block_device(device_path):
        logger.error("Not a block device: %s", device_path)
        raise NotBlockDeviceError(device_path)

    # Check if partition
    if is_partition_path(device_path):
        logger.error("Device is a partition: %s", device_path)
        raise PartitionDeviceError(device_path)

    # Check if system device
    if check_system_device:
        root_device = get_root_device()
        if root_device and device_path == root_device:
            logger.error("Device is system root: %s", device_path)
            raise SystemDeviceError(device_path)

    # Get mount points
    mount_points: list[str] = []
    is_mounted = False
    if check_mount:
        mount_points = get_mount_points(device_path)
        is_mounted = len(mount_points) > 0

        if is_mounted and not allow_mounted:
            logger.error("Device is mounted: %s at %s", device_path, mount_points)
            raise DeviceMountedError(device_path, mount_points)
        elif is_mounted:
            logger.warning(
                "Device %s has mounted partitions: %s", device_path, mount_points
            )

    # Get device info
    size_bytes = get_device_size(device_path)

    logger.info(
        "Device validated: %s (size=%s, mounted=%s)",
        device_path,
        size_bytes,
        is_mounted,
    )

    return DeviceInfo(
        path=device_path,
        is_block_device=True,
        is_whole_device=True,
        is_mounted=is_mounted,
        mount_points=mount_points,
        size_bytes=size_bytes,
    )


__all__ = [
    "DeviceInfo",
    "DeviceMountedError",
    "DeviceNotFoundError",
    "DeviceValidationError",
    "NotBlockDeviceError",
    "PartitionDeviceError",
    "SystemDeviceError",
    "get_device_size",
    "get_mount_points",
    "get_root_device",
    "is_block_device",
    "is_partition_path",
    "validate_device",
]
