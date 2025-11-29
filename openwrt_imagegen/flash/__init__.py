"""TF/SD card flashing module.

This module handles:
- Device validation (whole-device only)
- Safe write operations with fsync
- Hash-based verification
- Dry-run and force modes

All operations follow the safety rules in docs/SAFETY.md:
- Explicit device paths only (no guessing)
- Pre-flight checks and optional wipe
- Synchronous, flushed writes
- Hash verification after write
"""

from openwrt_imagegen.flash.device import (
    DeviceInfo,
    DeviceMountedError,
    DeviceNotFoundError,
    DeviceValidationError,
    NotBlockDeviceError,
    PartitionDeviceError,
    SystemDeviceError,
    validate_device,
)
from openwrt_imagegen.flash.models import FlashRecord
from openwrt_imagegen.flash.service import (
    ArtifactFileNotFoundError,
    ArtifactNotFoundError,
    FlashPlan,
    FlashResult,
    FlashServiceError,
    flash_artifact,
    flash_image,
    get_flash_records,
    plan_flash,
)
from openwrt_imagegen.flash.writer import (
    HashMismatchError,
    ImageNotFoundError,
    WriteError,
    WriteResult,
    compute_file_hash,
    write_image_to_device,
)

__all__ = [
    # Models
    "FlashRecord",
    # Device validation
    "DeviceInfo",
    "DeviceMountedError",
    "DeviceNotFoundError",
    "DeviceValidationError",
    "NotBlockDeviceError",
    "PartitionDeviceError",
    "SystemDeviceError",
    "validate_device",
    # Writer
    "HashMismatchError",
    "ImageNotFoundError",
    "WriteError",
    "WriteResult",
    "compute_file_hash",
    "write_image_to_device",
    # Service
    "ArtifactFileNotFoundError",
    "ArtifactNotFoundError",
    "FlashPlan",
    "FlashResult",
    "FlashServiceError",
    "flash_artifact",
    "flash_image",
    "get_flash_records",
    "plan_flash",
]
