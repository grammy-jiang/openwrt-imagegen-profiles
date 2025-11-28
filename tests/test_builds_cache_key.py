"""Tests for builds/cache_key.py module.

Tests cache key computation, input normalization, and deterministic hashing.
"""

import pytest

from openwrt_imagegen.builds.cache_key import (
    CACHE_KEY_SCHEMA_VERSION,
    BuildInputs,
    compute_cache_key,
    compute_cache_key_from_profile,
    compute_effective_packages,
    create_build_inputs,
    normalize_profile_snapshot,
)
from openwrt_imagegen.profiles.schema import ProfilePoliciesSchema, ProfileSchema


@pytest.fixture
def minimal_profile() -> ProfileSchema:
    """Create a minimal valid profile schema."""
    return ProfileSchema(
        profile_id="test.device.23.05",
        name="Test Device",
        device_id="test-device",
        openwrt_release="23.05.3",
        target="ath79",
        subtarget="generic",
        imagebuilder_profile="test-profile",
    )


@pytest.fixture
def full_profile() -> ProfileSchema:
    """Create a profile with all fields populated."""
    return ProfileSchema(
        profile_id="full.test.23.05",
        name="Full Test Profile",
        description="Test profile with all fields",
        device_id="full-test-device",
        tags=["test", "full", "example"],
        openwrt_release="23.05.3",
        target="ath79",
        subtarget="generic",
        imagebuilder_profile="full-test-profile",
        packages=["luci", "htop", "nano"],
        packages_remove=["ppp", "ppp-mod-pppoe"],
        bin_dir="/custom/output",
        extra_image_name="custom-build",
        disabled_services=["dnsmasq", "firewall"],
        rootfs_partsize=256,
        add_local_key=True,
        policies=ProfilePoliciesSchema(
            filesystem="squashfs",
            include_kernel_symbols=False,
            strip_debug=True,
        ),
    )


class TestNormalizeProfileSnapshot:
    """Tests for normalize_profile_snapshot function."""

    def test_minimal_profile(self, minimal_profile):
        """Should extract required fields from minimal profile."""
        snapshot = normalize_profile_snapshot(minimal_profile)

        assert snapshot["profile_id"] == "test.device.23.05"
        assert snapshot["openwrt_release"] == "23.05.3"
        assert snapshot["target"] == "ath79"
        assert snapshot["subtarget"] == "generic"
        assert snapshot["imagebuilder_profile"] == "test-profile"

        # Optional fields should not be present
        assert "packages" not in snapshot
        assert "packages_remove" not in snapshot
        assert "bin_dir" not in snapshot

    def test_full_profile(self, full_profile):
        """Should include all populated fields."""
        snapshot = normalize_profile_snapshot(full_profile)

        assert snapshot["profile_id"] == "full.test.23.05"
        assert snapshot["packages"] == sorted(["luci", "htop", "nano"])
        assert snapshot["packages_remove"] == sorted(["ppp", "ppp-mod-pppoe"])
        assert snapshot["bin_dir"] == "/custom/output"
        assert snapshot["extra_image_name"] == "custom-build"
        assert snapshot["disabled_services"] == sorted(["dnsmasq", "firewall"])
        assert snapshot["rootfs_partsize"] == 256
        assert snapshot["add_local_key"] is True
        assert snapshot["policies"]["filesystem"] == "squashfs"

    def test_packages_sorted(self):
        """Should sort packages for determinism."""
        profile = ProfileSchema(
            profile_id="test.sort",
            name="Sort Test",
            device_id="sort-device",
            openwrt_release="23.05.3",
            target="ath79",
            subtarget="generic",
            imagebuilder_profile="sort-profile",
            packages=["zsh", "nano", "htop", "luci"],
        )

        snapshot = normalize_profile_snapshot(profile)
        assert snapshot["packages"] == ["htop", "luci", "nano", "zsh"]

    def test_disabled_services_sorted(self):
        """Should sort disabled_services for determinism."""
        profile = ProfileSchema(
            profile_id="test.svc",
            name="Services Test",
            device_id="svc-device",
            openwrt_release="23.05.3",
            target="ath79",
            subtarget="generic",
            imagebuilder_profile="svc-profile",
            disabled_services=["firewall", "dnsmasq", "dropbear"],
        )

        snapshot = normalize_profile_snapshot(profile)
        assert snapshot["disabled_services"] == ["dnsmasq", "dropbear", "firewall"]


class TestComputeEffectivePackages:
    """Tests for compute_effective_packages function."""

    def test_packages_only(self, minimal_profile):
        """Should return packages as-is when no removals."""
        profile = ProfileSchema(
            **{
                **minimal_profile.model_dump(),
                "packages": ["luci", "htop"],
            }
        )
        result = compute_effective_packages(profile)
        assert sorted(result) == ["htop", "luci"]

    def test_removals_only(self, minimal_profile):
        """Should prefix removals with '-'."""
        profile = ProfileSchema(
            **{
                **minimal_profile.model_dump(),
                "packages_remove": ["ppp", "ppp-mod-pppoe"],
            }
        )
        result = compute_effective_packages(profile)
        assert sorted(result) == ["-ppp", "-ppp-mod-pppoe"]

    def test_packages_and_removals(self, minimal_profile):
        """Should combine packages and removals."""
        profile = ProfileSchema(
            **{
                **minimal_profile.model_dump(),
                "packages": ["luci", "htop"],
                "packages_remove": ["ppp"],
            }
        )
        result = compute_effective_packages(profile)
        assert sorted(result) == ["-ppp", "htop", "luci"]

    def test_extra_packages(self, minimal_profile):
        """Should include extra packages."""
        profile = ProfileSchema(
            **{
                **minimal_profile.model_dump(),
                "packages": ["luci"],
            }
        )
        result = compute_effective_packages(
            profile, extra_packages=["tcpdump", "iperf3"]
        )
        assert sorted(result) == ["iperf3", "luci", "tcpdump"]

    def test_removal_overrides_package(self, minimal_profile):
        """Should remove package if in packages_remove."""
        profile = ProfileSchema(
            **{
                **minimal_profile.model_dump(),
                "packages": ["luci", "ppp"],
                "packages_remove": ["ppp"],
            }
        )
        result = compute_effective_packages(profile)
        # ppp should be removed and -ppp added
        assert "-ppp" in result
        assert "ppp" not in result
        assert "luci" in result

    def test_empty_profile(self, minimal_profile):
        """Should return empty list for profile without packages."""
        result = compute_effective_packages(minimal_profile)
        assert result == []


class TestBuildInputs:
    """Tests for BuildInputs dataclass."""

    def test_default_values(self):
        """Should have appropriate defaults."""
        inputs = BuildInputs()
        assert inputs.schema_version == CACHE_KEY_SCHEMA_VERSION
        assert inputs.profile_snapshot == {}
        assert inputs.imagebuilder_key == ("", "", "")
        assert inputs.effective_packages == []
        assert inputs.overlay_hash is None
        assert inputs.build_options == {}

    def test_to_dict_conversion(self):
        """Should convert to dict for JSON serialization."""
        inputs = BuildInputs(
            profile_snapshot={"profile_id": "test"},
            imagebuilder_key=("23.05.3", "ath79", "generic"),
            effective_packages=["luci"],
        )
        result = inputs.to_dict()

        assert result["schema_version"] == CACHE_KEY_SCHEMA_VERSION
        assert result["imagebuilder_key"] == [
            "23.05.3",
            "ath79",
            "generic",
        ]  # list, not tuple
        assert result["profile_snapshot"] == {"profile_id": "test"}


class TestCreateBuildInputs:
    """Tests for create_build_inputs function."""

    def test_minimal_profile(self, minimal_profile):
        """Should create inputs from minimal profile."""
        inputs = create_build_inputs(minimal_profile)

        assert inputs.schema_version == CACHE_KEY_SCHEMA_VERSION
        assert inputs.imagebuilder_key == ("23.05.3", "ath79", "generic")
        assert inputs.profile_snapshot["profile_id"] == "test.device.23.05"
        assert inputs.overlay_hash is None
        assert inputs.build_options == {}

    def test_with_overlay_hash(self, minimal_profile):
        """Should include overlay hash."""
        inputs = create_build_inputs(
            minimal_profile,
            overlay_hash="abc123def456",
        )
        assert inputs.overlay_hash == "abc123def456"

    def test_with_extra_packages(self, minimal_profile):
        """Should include extra packages in effective packages."""
        inputs = create_build_inputs(
            minimal_profile,
            extra_packages=["tcpdump"],
        )
        assert "tcpdump" in inputs.effective_packages

    def test_with_build_options(self, minimal_profile):
        """Should include build options."""
        inputs = create_build_inputs(
            minimal_profile,
            build_options={"custom_option": True},
        )
        assert inputs.build_options == {"custom_option": True}


class TestComputeCacheKey:
    """Tests for compute_cache_key function."""

    def test_basic_key_format(self):
        """Should return sha256:... format."""
        inputs = BuildInputs()
        key = compute_cache_key(inputs)
        assert key.startswith("sha256:")
        assert len(key) == 7 + 64  # "sha256:" + 64 hex chars

    def test_deterministic(self, minimal_profile):
        """Should produce identical keys for identical inputs."""
        inputs1 = create_build_inputs(minimal_profile)
        inputs2 = create_build_inputs(minimal_profile)

        key1 = compute_cache_key(inputs1)
        key2 = compute_cache_key(inputs2)

        assert key1 == key2

    def test_different_profiles_different_keys(self, minimal_profile, full_profile):
        """Should produce different keys for different profiles."""
        inputs1 = create_build_inputs(minimal_profile)
        inputs2 = create_build_inputs(full_profile)

        key1 = compute_cache_key(inputs1)
        key2 = compute_cache_key(inputs2)

        assert key1 != key2

    def test_overlay_hash_affects_key(self, minimal_profile):
        """Should produce different keys when overlay hash differs."""
        inputs1 = create_build_inputs(minimal_profile, overlay_hash="hash1")
        inputs2 = create_build_inputs(minimal_profile, overlay_hash="hash2")

        key1 = compute_cache_key(inputs1)
        key2 = compute_cache_key(inputs2)

        assert key1 != key2

    def test_extra_packages_affect_key(self, minimal_profile):
        """Should produce different keys when extra packages differ."""
        inputs1 = create_build_inputs(minimal_profile, extra_packages=["pkg1"])
        inputs2 = create_build_inputs(minimal_profile, extra_packages=["pkg2"])

        key1 = compute_cache_key(inputs1)
        key2 = compute_cache_key(inputs2)

        assert key1 != key2


class TestComputeCacheKeyFromProfile:
    """Tests for compute_cache_key_from_profile convenience function."""

    def test_returns_tuple(self, minimal_profile):
        """Should return tuple of (key, inputs)."""
        result = compute_cache_key_from_profile(minimal_profile)
        assert isinstance(result, tuple)
        assert len(result) == 2

        key, inputs = result
        assert isinstance(key, str)
        assert isinstance(inputs, BuildInputs)

    def test_consistent_with_components(self, minimal_profile):
        """Should produce same key as manual workflow."""
        key1, inputs1 = compute_cache_key_from_profile(minimal_profile)

        inputs2 = create_build_inputs(minimal_profile)
        key2 = compute_cache_key(inputs2)

        assert key1 == key2

    def test_with_all_options(self, minimal_profile):
        """Should handle all optional parameters."""
        key, inputs = compute_cache_key_from_profile(
            minimal_profile,
            overlay_hash="testhash",
            extra_packages=["pkg1", "pkg2"],
            build_options={"opt1": "val1"},
        )

        assert inputs.overlay_hash == "testhash"
        assert "pkg1" in inputs.effective_packages
        assert inputs.build_options == {"opt1": "val1"}
