"""Tests for flash/device.py - device validation."""

import stat
import tempfile
from unittest.mock import mock_open, patch

import pytest

from openwrt_imagegen.flash.device import (
    DeviceInfo,
    DeviceMountedError,
    DeviceNotFoundError,
    NotBlockDeviceError,
    PartitionDeviceError,
    SystemDeviceError,
    _partition_to_whole_device,
    get_device_size,
    get_mount_points,
    get_root_device,
    is_block_device,
    is_partition_path,
    validate_device,
)


class TestIsPartitionPath:
    """Tests for is_partition_path function."""

    def test_whole_device_sd(self):
        """Whole disk device should not be detected as partition."""
        assert is_partition_path("/dev/sda") is False
        assert is_partition_path("/dev/sdb") is False
        assert is_partition_path("/dev/sdz") is False

    def test_partition_sd(self):
        """SCSI/SATA partitions should be detected."""
        assert is_partition_path("/dev/sda1") is True
        assert is_partition_path("/dev/sdb2") is True
        assert is_partition_path("/dev/sdz10") is True

    def test_whole_device_mmcblk(self):
        """MMC whole device should not be detected as partition."""
        assert is_partition_path("/dev/mmcblk0") is False
        assert is_partition_path("/dev/mmcblk1") is False

    def test_partition_mmcblk(self):
        """MMC partitions should be detected."""
        assert is_partition_path("/dev/mmcblk0p1") is True
        assert is_partition_path("/dev/mmcblk1p2") is True

    def test_whole_device_nvme(self):
        """NVMe whole device should not be detected as partition."""
        assert is_partition_path("/dev/nvme0n1") is False
        assert is_partition_path("/dev/nvme1n1") is False

    def test_partition_nvme(self):
        """NVMe partitions should be detected."""
        assert is_partition_path("/dev/nvme0n1p1") is True
        assert is_partition_path("/dev/nvme0n1p2") is True

    def test_whole_device_loop(self):
        """Loop device should not be detected as partition."""
        assert is_partition_path("/dev/loop0") is False
        assert is_partition_path("/dev/loop1") is False

    def test_partition_loop(self):
        """Loop device partitions should be detected."""
        assert is_partition_path("/dev/loop0p1") is True
        assert is_partition_path("/dev/loop1p2") is True

    def test_regular_file(self):
        """Regular file paths should not be detected as partition."""
        assert is_partition_path("/tmp/test.img") is False
        assert is_partition_path("/home/user/disk.bin") is False


class TestPartitionToWholeDevice:
    """Tests for _partition_to_whole_device function."""

    def test_sd_partition(self):
        """Convert SCSI/SATA partition to whole device."""
        assert _partition_to_whole_device("/dev/sda1") == "/dev/sda"
        assert _partition_to_whole_device("/dev/sdb12") == "/dev/sdb"

    def test_mmcblk_partition(self):
        """Convert MMC partition to whole device."""
        assert _partition_to_whole_device("/dev/mmcblk0p1") == "/dev/mmcblk0"
        assert _partition_to_whole_device("/dev/mmcblk1p2") == "/dev/mmcblk1"

    def test_nvme_partition(self):
        """Convert NVMe partition to whole device."""
        assert _partition_to_whole_device("/dev/nvme0n1p1") == "/dev/nvme0n1"
        assert _partition_to_whole_device("/dev/nvme1n1p2") == "/dev/nvme1n1"

    def test_loop_partition(self):
        """Convert loop partition to whole device."""
        assert _partition_to_whole_device("/dev/loop0p1") == "/dev/loop0"

    def test_whole_device_unchanged(self):
        """Whole device paths should be returned as-is."""
        assert _partition_to_whole_device("/dev/sda") == "/dev/sda"
        assert _partition_to_whole_device("/dev/mmcblk0") == "/dev/mmcblk0"


class TestIsBlockDevice:
    """Tests for is_block_device function."""

    def test_regular_file(self):
        """Regular file should not be a block device."""
        with tempfile.NamedTemporaryFile() as f:
            assert is_block_device(f.name) is False

    def test_directory(self):
        """Directory should not be a block device."""
        with tempfile.TemporaryDirectory() as d:
            assert is_block_device(d) is False

    def test_nonexistent_path(self):
        """Non-existent path should return False."""
        assert is_block_device("/dev/nonexistent_device_xyz123") is False

    def test_block_device_mock(self):
        """Mocked block device should be detected."""
        # Mock os.stat to return a block device mode
        block_mode = stat.S_IFBLK | 0o660
        with patch("os.stat") as mock_stat:
            mock_stat.return_value.st_mode = block_mode
            assert is_block_device("/dev/fake_block") is True


class TestGetMountPoints:
    """Tests for get_mount_points function."""

    def test_no_mounts(self):
        """Device with no mounts should return empty list."""
        proc_mounts = """/dev/sda1 / ext4 rw 0 0
/dev/sda2 /home ext4 rw 0 0
"""
        with patch("builtins.open", mock_open(read_data=proc_mounts)):
            # sdb has no mounts
            result = get_mount_points("/dev/sdb")
            assert result == []

    def test_with_mounts(self):
        """Device with mounts should return mount points."""
        proc_mounts = """/dev/sda1 / ext4 rw 0 0
/dev/sda2 /home ext4 rw 0 0
/dev/sdb1 /mnt/usb ext4 rw 0 0
"""
        with patch("builtins.open", mock_open(read_data=proc_mounts)):
            result = get_mount_points("/dev/sdb")
            assert result == ["/mnt/usb"]

    def test_multiple_partitions_mounted(self):
        """Device with multiple mounted partitions."""
        proc_mounts = """/dev/sda1 / ext4 rw 0 0
/dev/sdb1 /mnt/data1 ext4 rw 0 0
/dev/sdb2 /mnt/data2 ext4 rw 0 0
"""
        with patch("builtins.open", mock_open(read_data=proc_mounts)):
            result = get_mount_points("/dev/sdb")
            assert set(result) == {"/mnt/data1", "/mnt/data2"}

    def test_read_error(self):
        """Handle /proc/mounts read error gracefully."""
        with patch("builtins.open", side_effect=OSError("Permission denied")):
            result = get_mount_points("/dev/sda")
            assert result == []


class TestGetRootDevice:
    """Tests for get_root_device function."""

    def test_simple_sd_root(self):
        """Simple SCSI root device detection."""
        proc_mounts = """/dev/sda1 / ext4 rw 0 0
/dev/sda2 /home ext4 rw 0 0
"""
        with patch("builtins.open", mock_open(read_data=proc_mounts)):
            result = get_root_device()
            assert result == "/dev/sda"

    def test_nvme_root(self):
        """NVMe root device detection."""
        proc_mounts = """/dev/nvme0n1p1 / ext4 rw 0 0
/dev/nvme0n1p2 /home ext4 rw 0 0
"""
        with patch("builtins.open", mock_open(read_data=proc_mounts)):
            result = get_root_device()
            assert result == "/dev/nvme0n1"

    def test_mmcblk_root(self):
        """MMC root device detection."""
        proc_mounts = """/dev/mmcblk0p1 / ext4 rw 0 0
"""
        with patch("builtins.open", mock_open(read_data=proc_mounts)):
            result = get_root_device()
            assert result == "/dev/mmcblk0"

    def test_read_error(self):
        """Handle /proc/mounts read error gracefully."""
        with patch("builtins.open", side_effect=OSError("Permission denied")):
            result = get_root_device()
            assert result is None


class TestGetDeviceSize:
    """Tests for get_device_size function."""

    def test_sysfs_read(self):
        """Read device size from sysfs."""
        # 1000 sectors * 512 bytes = 512000 bytes
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", return_value="1000\n"):
                result = get_device_size("/dev/sda")
                assert result == 512000

    def test_sysfs_not_found(self):
        """Return None if sysfs path doesn't exist."""
        with patch("pathlib.Path.exists", return_value=False):
            result = get_device_size("/dev/nonexistent")
            assert result is None

    def test_read_error(self):
        """Return None on read error."""
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", side_effect=OSError("Error")):
                result = get_device_size("/dev/sda")
                assert result is None


class TestValidateDevice:
    """Tests for validate_device function."""

    def test_device_not_found(self):
        """Raise DeviceNotFoundError for non-existent device."""
        with pytest.raises(DeviceNotFoundError) as exc_info:
            validate_device("/dev/nonexistent_device_xyz")

        assert "not found" in str(exc_info.value).lower()
        assert exc_info.value.error_code == "DEVICE_NOT_FOUND"

    def test_not_block_device(self):
        """Raise NotBlockDeviceError for non-block device."""
        with tempfile.NamedTemporaryFile() as f:
            with pytest.raises(NotBlockDeviceError) as exc_info:
                validate_device(f.name)

            assert "not a block device" in str(exc_info.value).lower()
            assert exc_info.value.error_code == "NOT_BLOCK_DEVICE"

    def test_partition_not_allowed(self):
        """Raise PartitionDeviceError for partition paths."""
        # Mock the device to exist and be a block device
        block_mode = stat.S_IFBLK | 0o660
        with patch("os.path.exists", return_value=True):
            with patch("os.stat") as mock_stat:
                mock_stat.return_value.st_mode = block_mode
                with pytest.raises(PartitionDeviceError) as exc_info:
                    validate_device("/dev/sda1")

                assert "partition" in str(exc_info.value).lower()
                assert exc_info.value.error_code == "PARTITION_NOT_ALLOWED"

    def test_system_device_rejected(self):
        """Raise SystemDeviceError for system root device."""
        proc_mounts = "/dev/sda1 / ext4 rw 0 0\n"
        block_mode = stat.S_IFBLK | 0o660

        with patch("os.path.exists", return_value=True):
            with patch("os.stat") as mock_stat:
                mock_stat.return_value.st_mode = block_mode
                with patch("builtins.open", mock_open(read_data=proc_mounts)):
                    with pytest.raises(SystemDeviceError) as exc_info:
                        validate_device("/dev/sda")

                    assert "system root" in str(exc_info.value).lower()
                    assert exc_info.value.error_code == "SYSTEM_DEVICE"

    def test_mounted_device_rejected(self):
        """Raise DeviceMountedError when device is mounted."""
        proc_mounts = "/dev/sdb1 /mnt/usb ext4 rw 0 0\n"
        block_mode = stat.S_IFBLK | 0o660

        with patch("os.path.exists", return_value=True):
            with patch("os.stat") as mock_stat:
                mock_stat.return_value.st_mode = block_mode
                with patch("builtins.open", mock_open(read_data=proc_mounts)):
                    with patch(
                        "openwrt_imagegen.flash.device.get_root_device",
                        return_value="/dev/sda",
                    ):
                        with pytest.raises(DeviceMountedError) as exc_info:
                            validate_device("/dev/sdb")

                        assert "mounted" in str(exc_info.value).lower()
                        assert exc_info.value.error_code == "DEVICE_MOUNTED"
                        assert exc_info.value.mount_points == ["/mnt/usb"]

    def test_mounted_device_allowed(self):
        """Allow mounted device when allow_mounted=True."""
        proc_mounts = "/dev/sdb1 /mnt/usb ext4 rw 0 0\n"
        block_mode = stat.S_IFBLK | 0o660

        with patch("os.path.exists", return_value=True):
            with patch("os.stat") as mock_stat:
                mock_stat.return_value.st_mode = block_mode
                with patch("builtins.open", mock_open(read_data=proc_mounts)):
                    with patch(
                        "openwrt_imagegen.flash.device.get_root_device",
                        return_value="/dev/sda",
                    ):
                        with patch(
                            "openwrt_imagegen.flash.device.get_device_size",
                            return_value=1000000,
                        ):
                            result = validate_device("/dev/sdb", allow_mounted=True)

                            assert isinstance(result, DeviceInfo)
                            assert result.is_mounted is True
                            assert result.mount_points == ["/mnt/usb"]

    def test_valid_device(self):
        """Successfully validate a proper device."""
        proc_mounts = "/dev/sda1 / ext4 rw 0 0\n"  # sdb not mounted
        block_mode = stat.S_IFBLK | 0o660

        with patch("os.path.exists", return_value=True):
            with patch("os.stat") as mock_stat:
                mock_stat.return_value.st_mode = block_mode
                with patch("builtins.open", mock_open(read_data=proc_mounts)):
                    with patch(
                        "openwrt_imagegen.flash.device.get_root_device",
                        return_value="/dev/sda",
                    ):
                        with patch(
                            "openwrt_imagegen.flash.device.get_device_size",
                            return_value=4000000000,
                        ):
                            result = validate_device("/dev/sdb")

                            assert isinstance(result, DeviceInfo)
                            assert result.is_block_device is True
                            assert result.is_whole_device is True
                            assert result.is_mounted is False
                            assert result.mount_points == []
                            assert result.size_bytes == 4000000000

    def test_skip_system_device_check(self):
        """Allow system device check to be skipped."""
        proc_mounts = "/dev/sda1 / ext4 rw 0 0\n"
        block_mode = stat.S_IFBLK | 0o660

        with patch("os.path.exists", return_value=True):
            with patch("os.stat") as mock_stat:
                mock_stat.return_value.st_mode = block_mode
                with patch("builtins.open", mock_open(read_data=proc_mounts)):
                    with patch(
                        "openwrt_imagegen.flash.device.get_device_size",
                        return_value=100000,
                    ):
                        # This would normally fail for system device
                        result = validate_device(
                            "/dev/sda",
                            check_system_device=False,
                            check_mount=False,
                        )
                        assert result.is_block_device is True
