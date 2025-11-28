"""Tests for profile schema validation.

These tests verify the Pydantic schema models for profile validation.
"""

import pytest
from pydantic import ValidationError

from openwrt_imagegen.profiles.schema import (
    BuildDefaultsSchema,
    FileSpecSchema,
    ProfilePoliciesSchema,
    ProfileSchema,
)


class TestFileSpecSchema:
    """Test FileSpecSchema validation."""

    def test_valid_file_spec(self):
        """Should accept valid file spec."""
        spec = FileSpecSchema(
            source="profiles/files/test/etc/banner",
            destination="/etc/banner",
            mode="0644",
            owner="root:root",
        )
        assert spec.source == "profiles/files/test/etc/banner"
        assert spec.destination == "/etc/banner"
        assert spec.mode == "0644"
        assert spec.owner == "root:root"

    def test_minimal_file_spec(self):
        """Should accept minimal file spec."""
        spec = FileSpecSchema(
            source="test.txt",
            destination="/test.txt",
        )
        assert spec.source == "test.txt"
        assert spec.destination == "/test.txt"
        assert spec.mode is None
        assert spec.owner is None

    def test_destination_must_start_with_slash(self):
        """Should reject destination not starting with /."""
        with pytest.raises(ValidationError) as exc_info:
            FileSpecSchema(source="test.txt", destination="etc/banner")
        assert "destination must start with '/'" in str(exc_info.value)

    def test_valid_mode_formats(self):
        """Should accept valid octal mode formats."""
        for mode in ["0644", "0755", "0600", "755", "644", "0777"]:
            spec = FileSpecSchema(source="test", destination="/test", mode=mode)
            assert spec.mode == mode

    def test_invalid_mode_format(self):
        """Should reject invalid mode formats."""
        with pytest.raises(ValidationError) as exc_info:
            FileSpecSchema(source="test", destination="/test", mode="invalid")
        assert "valid octal string" in str(exc_info.value)

    def test_invalid_mode_digits(self):
        """Should reject mode with invalid octal digits."""
        with pytest.raises(ValidationError) as exc_info:
            FileSpecSchema(source="test", destination="/test", mode="0894")
        assert "valid octal string" in str(exc_info.value)


class TestProfilePoliciesSchema:
    """Test ProfilePoliciesSchema validation."""

    def test_valid_policies(self):
        """Should accept valid policies."""
        policies = ProfilePoliciesSchema(
            filesystem="squashfs",
            include_kernel_symbols=True,
            strip_debug=False,
            auto_resize_rootfs=True,
            allow_snapshot=False,
        )
        assert policies.filesystem == "squashfs"
        assert policies.include_kernel_symbols is True
        assert policies.strip_debug is False

    def test_empty_policies(self):
        """Should accept empty policies."""
        policies = ProfilePoliciesSchema()
        assert policies.filesystem is None
        assert policies.include_kernel_symbols is None

    def test_valid_filesystem_values(self):
        """Should accept valid filesystem values."""
        for fs in ["squashfs", "ext4"]:
            policies = ProfilePoliciesSchema(filesystem=fs)
            assert policies.filesystem == fs

    def test_invalid_filesystem_value(self):
        """Should reject invalid filesystem values."""
        with pytest.raises(ValidationError) as exc_info:
            ProfilePoliciesSchema(filesystem="ntfs")
        assert "must be one of" in str(exc_info.value)


class TestBuildDefaultsSchema:
    """Test BuildDefaultsSchema validation."""

    def test_valid_build_defaults(self):
        """Should accept valid build defaults."""
        defaults = BuildDefaultsSchema(
            rebuild_if_cached=True,
            initramfs=False,
            keep_build_dir=True,
        )
        assert defaults.rebuild_if_cached is True
        assert defaults.initramfs is False
        assert defaults.keep_build_dir is True

    def test_empty_build_defaults(self):
        """Should accept empty build defaults."""
        defaults = BuildDefaultsSchema()
        assert defaults.rebuild_if_cached is None


class TestProfileSchema:
    """Test ProfileSchema validation."""

    @pytest.fixture
    def minimal_profile_data(self):
        """Return minimal valid profile data."""
        return {
            "profile_id": "test.device.release",
            "name": "Test Device Profile",
            "device_id": "test-device",
            "openwrt_release": "23.05.3",
            "target": "ath79",
            "subtarget": "generic",
            "imagebuilder_profile": "tplink_archer-c6-v3",
        }

    @pytest.fixture
    def full_profile_data(self):
        """Return full valid profile data."""
        return {
            "profile_id": "test.device.full",
            "name": "Full Test Profile",
            "description": "A complete test profile",
            "device_id": "test-device-full",
            "tags": ["test", "full", "example"],
            "openwrt_release": "23.05.3",
            "target": "ath79",
            "subtarget": "generic",
            "imagebuilder_profile": "tplink_archer-c6-v3",
            "packages": ["luci", "luci-ssl", "htop"],
            "packages_remove": ["ppp", "ppp-mod-pppoe"],
            "files": [
                {
                    "source": "profiles/files/test/etc/banner",
                    "destination": "/etc/banner",
                    "mode": "0644",
                    "owner": "root:root",
                }
            ],
            "overlay_dir": "profiles/overlays/test",
            "policies": {
                "filesystem": "squashfs",
                "include_kernel_symbols": False,
                "strip_debug": True,
            },
            "build_defaults": {
                "rebuild_if_cached": False,
                "initramfs": False,
            },
            "bin_dir": "/var/tmp/images",
            "extra_image_name": "test",
            "disabled_services": ["dnsmasq"],
            "rootfs_partsize": 128,
            "add_local_key": True,
            "created_by": "test",
            "notes": "Test notes",
        }

    def test_minimal_profile(self, minimal_profile_data):
        """Should accept minimal profile."""
        profile = ProfileSchema.model_validate(minimal_profile_data)
        assert profile.profile_id == "test.device.release"
        assert profile.name == "Test Device Profile"
        assert profile.packages is None
        assert profile.policies is None

    def test_full_profile(self, full_profile_data):
        """Should accept full profile."""
        profile = ProfileSchema.model_validate(full_profile_data)
        assert profile.profile_id == "test.device.full"
        assert profile.packages == ["luci", "luci-ssl", "htop"]
        assert profile.policies is not None
        assert profile.policies.filesystem == "squashfs"
        assert profile.files is not None
        assert len(profile.files) == 1
        assert profile.rootfs_partsize == 128

    def test_missing_required_field(self, minimal_profile_data):
        """Should reject profile missing required field."""
        del minimal_profile_data["profile_id"]
        with pytest.raises(ValidationError) as exc_info:
            ProfileSchema.model_validate(minimal_profile_data)
        assert "profile_id" in str(exc_info.value)

    def test_invalid_profile_id_pattern(self):
        """Should reject profile_id with invalid characters."""
        with pytest.raises(ValidationError) as exc_info:
            ProfileSchema(
                profile_id="test/invalid/id",
                name="Test",
                device_id="test",
                openwrt_release="23.05",
                target="ath79",
                subtarget="generic",
                imagebuilder_profile="test",
            )
        assert "must match pattern" in str(exc_info.value)

    def test_valid_profile_id_patterns(self):
        """Should accept valid profile_id patterns."""
        valid_ids = [
            "test.device.23.05",
            "home-ap-livingroom",
            "lab_router_1",
            "MyDevice.v2.0",
            "a123.b456_c789-d012",
        ]
        for pid in valid_ids:
            profile = ProfileSchema(
                profile_id=pid,
                name="Test",
                device_id="test",
                openwrt_release="23.05",
                target="ath79",
                subtarget="generic",
                imagebuilder_profile="test",
            )
            assert profile.profile_id == pid

    def test_empty_profile_id(self):
        """Should reject empty profile_id."""
        with pytest.raises(ValidationError):
            ProfileSchema(
                profile_id="",
                name="Test",
                device_id="test",
                openwrt_release="23.05",
                target="ath79",
                subtarget="generic",
                imagebuilder_profile="test",
            )

    def test_empty_tags(self):
        """Should reject empty string tags."""
        with pytest.raises(ValidationError) as exc_info:
            ProfileSchema(
                profile_id="test",
                name="Test",
                device_id="test",
                tags=["valid", "", "another"],
                openwrt_release="23.05",
                target="ath79",
                subtarget="generic",
                imagebuilder_profile="test",
            )
        assert "non-empty strings" in str(exc_info.value)

    def test_too_many_tags(self):
        """Should reject too many tags."""
        with pytest.raises(ValidationError) as exc_info:
            ProfileSchema(
                profile_id="test",
                name="Test",
                device_id="test",
                tags=[f"tag{i}" for i in range(100)],
                openwrt_release="23.05",
                target="ath79",
                subtarget="generic",
                imagebuilder_profile="test",
            )
        assert "too many tags" in str(exc_info.value)

    def test_package_with_whitespace(self):
        """Should reject packages with whitespace."""
        with pytest.raises(ValidationError) as exc_info:
            ProfileSchema(
                profile_id="test",
                name="Test",
                device_id="test",
                packages=["luci", "invalid package"],
                openwrt_release="23.05",
                target="ath79",
                subtarget="generic",
                imagebuilder_profile="test",
            )
        assert "whitespace" in str(exc_info.value)

    def test_empty_package_name(self):
        """Should reject empty package names."""
        with pytest.raises(ValidationError) as exc_info:
            ProfileSchema(
                profile_id="test",
                name="Test",
                device_id="test",
                packages=["luci", "", "htop"],
                openwrt_release="23.05",
                target="ath79",
                subtarget="generic",
                imagebuilder_profile="test",
            )
        assert "non-empty strings" in str(exc_info.value)

    def test_rootfs_partsize_positive(self):
        """Should reject non-positive rootfs_partsize."""
        with pytest.raises(ValidationError):
            ProfileSchema(
                profile_id="test",
                name="Test",
                device_id="test",
                openwrt_release="23.05",
                target="ath79",
                subtarget="generic",
                imagebuilder_profile="test",
                rootfs_partsize=0,
            )

    def test_snapshot_policy_validation(self, minimal_profile_data):
        """Should validate snapshot policy consistency."""
        minimal_profile_data["openwrt_release"] = "snapshot"
        profile = ProfileSchema.model_validate(minimal_profile_data)

        # Without allow_snapshot policy, validation should fail
        with pytest.raises(ValueError) as exc_info:
            profile.validate_snapshot_policy()
        assert "requires policies.allow_snapshot=true" in str(exc_info.value)

    def test_snapshot_with_allow_snapshot_policy(self, minimal_profile_data):
        """Should accept snapshot with allow_snapshot=true."""
        minimal_profile_data["openwrt_release"] = "snapshot"
        minimal_profile_data["policies"] = {"allow_snapshot": True}
        profile = ProfileSchema.model_validate(minimal_profile_data)

        # Should not raise
        profile.validate_snapshot_policy()

    def test_extra_fields_rejected(self, minimal_profile_data):
        """Should reject extra fields not in schema."""
        minimal_profile_data["unknown_field"] = "value"
        with pytest.raises(ValidationError) as exc_info:
            ProfileSchema.model_validate(minimal_profile_data)
        assert "Extra inputs are not permitted" in str(exc_info.value)

    def test_nested_file_spec_validation(self, minimal_profile_data):
        """Should validate nested file specs."""
        minimal_profile_data["files"] = [
            {"source": "test", "destination": "no-leading-slash"}
        ]
        with pytest.raises(ValidationError) as exc_info:
            ProfileSchema.model_validate(minimal_profile_data)
        assert "destination must start with '/'" in str(exc_info.value)

    def test_model_dump_excludes_none(self, minimal_profile_data):
        """Should be able to dump model excluding None values."""
        profile = ProfileSchema.model_validate(minimal_profile_data)
        data = profile.model_dump(exclude_none=True)

        # Required fields present
        assert "profile_id" in data
        assert "name" in data

        # Optional None fields excluded
        assert "description" not in data
        assert "packages" not in data
