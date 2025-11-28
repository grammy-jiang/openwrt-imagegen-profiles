"""Tests for builds/runner.py module.

Tests build command composition and execution.
Uses mocked subprocess for build execution tests.
"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from openwrt_imagegen.builds.runner import (
    BuildExecutionError,
    BuildResult,
    compose_make_command,
    compose_packages_arg,
    run_build,
    validate_imagebuilder_root,
)
from openwrt_imagegen.profiles.schema import ProfileSchema


@pytest.fixture
def minimal_profile() -> ProfileSchema:
    """Create a minimal valid profile schema."""
    return ProfileSchema(
        profile_id="test.runner",
        name="Runner Test",
        device_id="runner-device",
        openwrt_release="23.05.3",
        target="ath79",
        subtarget="generic",
        imagebuilder_profile="test-profile",
    )


@pytest.fixture
def full_profile() -> ProfileSchema:
    """Create a profile with all build-related fields."""
    return ProfileSchema(
        profile_id="full.runner",
        name="Full Runner Test",
        device_id="full-runner-device",
        openwrt_release="23.05.3",
        target="ath79",
        subtarget="generic",
        imagebuilder_profile="full-test-profile",
        packages=["luci", "htop", "nano"],
        packages_remove=["ppp", "ppp-mod-pppoe"],
        extra_image_name="custom",
        disabled_services=["dnsmasq", "firewall"],
        rootfs_partsize=256,
        add_local_key=True,
    )


class TestComposePackagesArg:
    """Tests for compose_packages_arg function."""

    def test_packages_only(self):
        """Should join packages with spaces."""
        result = compose_packages_arg(["luci", "htop"], None, None)
        assert "luci" in result
        assert "htop" in result

    def test_packages_remove(self):
        """Should prefix removals with '-'."""
        result = compose_packages_arg(None, ["ppp"], None)
        assert "-ppp" in result

    def test_extra_packages(self):
        """Should include extra packages."""
        result = compose_packages_arg(["luci"], None, ["tcpdump"])
        assert "luci" in result
        assert "tcpdump" in result

    def test_combined(self):
        """Should combine all package sources."""
        result = compose_packages_arg(
            ["luci", "htop"],
            ["ppp"],
            ["tcpdump"],
        )
        assert "luci" in result
        assert "htop" in result
        assert "-ppp" in result
        assert "tcpdump" in result

    def test_removal_removes_from_packages(self):
        """Should remove package before adding as removal."""
        result = compose_packages_arg(
            ["luci", "ppp"],
            ["ppp"],
            None,
        )
        # Should have luci and -ppp, not ppp twice
        parts = result.split()
        assert "luci" in parts
        assert "-ppp" in parts
        assert parts.count("ppp") == 0

    def test_empty_returns_empty(self):
        """Should return empty string for no packages."""
        result = compose_packages_arg(None, None, None)
        assert result == ""


class TestComposeMakeCommand:
    """Tests for compose_make_command function."""

    def test_minimal_command(self, minimal_profile, tmp_path):
        """Should compose minimal command."""
        bin_dir = tmp_path / "bin"
        cmd = compose_make_command(minimal_profile, bin_dir)

        assert cmd[0] == "make"
        assert cmd[1] == "image"
        assert f"PROFILE={minimal_profile.imagebuilder_profile}" in cmd
        assert f"BIN_DIR={bin_dir}" in cmd

    def test_with_packages(self, tmp_path):
        """Should include PACKAGES argument."""
        profile = ProfileSchema(
            profile_id="test.pkg",
            name="Pkg Test",
            device_id="pkg-device",
            openwrt_release="23.05.3",
            target="ath79",
            subtarget="generic",
            imagebuilder_profile="pkg-profile",
            packages=["luci", "htop"],
        )

        cmd = compose_make_command(profile, tmp_path / "bin")
        packages_arg = [c for c in cmd if c.startswith("PACKAGES=")]
        assert len(packages_arg) == 1
        assert "luci" in packages_arg[0]
        assert "htop" in packages_arg[0]

    def test_with_packages_remove(self, tmp_path):
        """Should include removals with '-' prefix in PACKAGES."""
        profile = ProfileSchema(
            profile_id="test.rm",
            name="Remove Test",
            device_id="rm-device",
            openwrt_release="23.05.3",
            target="ath79",
            subtarget="generic",
            imagebuilder_profile="rm-profile",
            packages_remove=["ppp"],
        )

        cmd = compose_make_command(profile, tmp_path / "bin")
        packages_arg = [c for c in cmd if c.startswith("PACKAGES=")]
        assert len(packages_arg) == 1
        assert "-ppp" in packages_arg[0]

    def test_with_files_dir(self, tmp_path):
        """Should include FILES argument when files_dir provided."""
        files_dir = tmp_path / "files"
        files_dir.mkdir()

        profile = ProfileSchema(
            profile_id="test.files",
            name="Files Test",
            device_id="files-device",
            openwrt_release="23.05.3",
            target="ath79",
            subtarget="generic",
            imagebuilder_profile="files-profile",
        )

        cmd = compose_make_command(profile, tmp_path / "bin", files_dir=files_dir)
        files_arg = [c for c in cmd if c.startswith("FILES=")]
        assert len(files_arg) == 1

    def test_with_extra_image_name(self, tmp_path):
        """Should include EXTRA_IMAGE_NAME argument."""
        profile = ProfileSchema(
            profile_id="test.extra",
            name="Extra Test",
            device_id="extra-device",
            openwrt_release="23.05.3",
            target="ath79",
            subtarget="generic",
            imagebuilder_profile="extra-profile",
            extra_image_name="custom",
        )

        cmd = compose_make_command(profile, tmp_path / "bin")
        assert "EXTRA_IMAGE_NAME=custom" in cmd

    def test_extra_image_name_override(self, tmp_path):
        """Should allow overriding extra_image_name."""
        profile = ProfileSchema(
            profile_id="test.override",
            name="Override Test",
            device_id="override-device",
            openwrt_release="23.05.3",
            target="ath79",
            subtarget="generic",
            imagebuilder_profile="override-profile",
            extra_image_name="original",
        )

        cmd = compose_make_command(
            profile,
            tmp_path / "bin",
            extra_image_name="override",
        )
        assert "EXTRA_IMAGE_NAME=override" in cmd
        assert "EXTRA_IMAGE_NAME=original" not in cmd

    def test_with_disabled_services(self, tmp_path):
        """Should include DISABLED_SERVICES argument."""
        profile = ProfileSchema(
            profile_id="test.svc",
            name="Services Test",
            device_id="svc-device",
            openwrt_release="23.05.3",
            target="ath79",
            subtarget="generic",
            imagebuilder_profile="svc-profile",
            disabled_services=["dnsmasq", "firewall"],
        )

        cmd = compose_make_command(profile, tmp_path / "bin")
        svc_arg = [c for c in cmd if c.startswith("DISABLED_SERVICES=")]
        assert len(svc_arg) == 1
        assert "dnsmasq" in svc_arg[0]
        assert "firewall" in svc_arg[0]

    def test_with_rootfs_partsize(self, tmp_path):
        """Should include ROOTFS_PARTSIZE argument."""
        profile = ProfileSchema(
            profile_id="test.rootfs",
            name="Rootfs Test",
            device_id="rootfs-device",
            openwrt_release="23.05.3",
            target="ath79",
            subtarget="generic",
            imagebuilder_profile="rootfs-profile",
            rootfs_partsize=256,
        )

        cmd = compose_make_command(profile, tmp_path / "bin")
        assert "ROOTFS_PARTSIZE=256" in cmd

    def test_with_add_local_key(self, tmp_path):
        """Should include ADD_LOCAL_KEY argument when True."""
        profile = ProfileSchema(
            profile_id="test.key",
            name="Key Test",
            device_id="key-device",
            openwrt_release="23.05.3",
            target="ath79",
            subtarget="generic",
            imagebuilder_profile="key-profile",
            add_local_key=True,
        )

        cmd = compose_make_command(profile, tmp_path / "bin")
        assert "ADD_LOCAL_KEY=1" in cmd

    def test_without_add_local_key(self, tmp_path):
        """Should not include ADD_LOCAL_KEY when False or None."""
        profile = ProfileSchema(
            profile_id="test.nokey",
            name="No Key Test",
            device_id="nokey-device",
            openwrt_release="23.05.3",
            target="ath79",
            subtarget="generic",
            imagebuilder_profile="nokey-profile",
            add_local_key=False,
        )

        cmd = compose_make_command(profile, tmp_path / "bin")
        assert not any("ADD_LOCAL_KEY" in c for c in cmd)

    def test_full_profile_command(self, full_profile, tmp_path):
        """Should handle full profile with all options."""
        files_dir = tmp_path / "files"
        files_dir.mkdir()

        cmd = compose_make_command(
            full_profile,
            tmp_path / "bin",
            files_dir=files_dir,
            extra_packages=["tcpdump"],
        )

        assert "make" in cmd
        assert "image" in cmd
        assert f"PROFILE={full_profile.imagebuilder_profile}" in cmd
        assert any("PACKAGES=" in c for c in cmd)
        assert any("EXTRA_IMAGE_NAME=" in c for c in cmd)
        assert any("DISABLED_SERVICES=" in c for c in cmd)
        assert "ROOTFS_PARTSIZE=256" in cmd
        assert "ADD_LOCAL_KEY=1" in cmd


class TestValidateImagebuilderRoot:
    """Tests for validate_imagebuilder_root function."""

    def test_valid_structure(self, tmp_path):
        """Should return True for valid structure."""
        root = tmp_path / "imagebuilder"
        root.mkdir()
        (root / "Makefile").touch()
        (root / "target").mkdir()
        (root / "packages").mkdir()

        assert validate_imagebuilder_root(root) is True

    def test_missing_directory(self, tmp_path):
        """Should return False for nonexistent directory."""
        assert validate_imagebuilder_root(tmp_path / "nonexistent") is False

    def test_not_a_directory(self, tmp_path):
        """Should return False for file instead of directory."""
        file_path = tmp_path / "file"
        file_path.touch()
        assert validate_imagebuilder_root(file_path) is False

    def test_missing_makefile(self, tmp_path):
        """Should return False without Makefile."""
        root = tmp_path / "imagebuilder"
        root.mkdir()
        (root / "target").mkdir()
        (root / "packages").mkdir()

        assert validate_imagebuilder_root(root) is False

    def test_missing_target_dir(self, tmp_path):
        """Should return False without target directory."""
        root = tmp_path / "imagebuilder"
        root.mkdir()
        (root / "Makefile").touch()
        (root / "packages").mkdir()

        assert validate_imagebuilder_root(root) is False

    def test_missing_packages_dir(self, tmp_path):
        """Should return False without packages directory."""
        root = tmp_path / "imagebuilder"
        root.mkdir()
        (root / "Makefile").touch()
        (root / "target").mkdir()

        assert validate_imagebuilder_root(root) is False


class TestRunBuild:
    """Tests for run_build function with mocked subprocess."""

    @pytest.fixture
    def valid_imagebuilder(self, tmp_path):
        """Create a valid (mock) Image Builder directory."""
        root = tmp_path / "imagebuilder"
        root.mkdir()
        (root / "Makefile").touch()
        (root / "target").mkdir()
        (root / "packages").mkdir()
        return root

    def test_successful_build(self, minimal_profile, valid_imagebuilder, tmp_path):
        """Should handle successful build."""
        build_dir = tmp_path / "build"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            result = run_build(
                profile=minimal_profile,
                imagebuilder_root=valid_imagebuilder,
                build_dir=build_dir,
            )

            assert isinstance(result, BuildResult)
            assert result.success is True
            assert result.exit_code == 0
            assert result.log_path.exists()

    def test_failed_build(self, minimal_profile, valid_imagebuilder, tmp_path):
        """Should handle failed build."""
        build_dir = tmp_path / "build"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)

            result = run_build(
                profile=minimal_profile,
                imagebuilder_root=valid_imagebuilder,
                build_dir=build_dir,
            )

            assert result.success is False
            assert result.exit_code == 1
            assert result.error_message is not None

    def test_timeout(self, minimal_profile, valid_imagebuilder, tmp_path):
        """Should raise on timeout."""
        build_dir = tmp_path / "build"

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="make", timeout=10)

            with pytest.raises(BuildExecutionError) as exc_info:
                run_build(
                    profile=minimal_profile,
                    imagebuilder_root=valid_imagebuilder,
                    build_dir=build_dir,
                    timeout=10,
                )

            assert exc_info.value.code == "build_timeout"

    def test_creates_directories(self, minimal_profile, valid_imagebuilder, tmp_path):
        """Should create build directories."""
        build_dir = tmp_path / "deep" / "nested" / "build"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            result = run_build(
                profile=minimal_profile,
                imagebuilder_root=valid_imagebuilder,
                build_dir=build_dir,
            )

            assert build_dir.exists()
            assert result.bin_dir.exists()

    def test_log_file_content(self, minimal_profile, valid_imagebuilder, tmp_path):
        """Should write command to log file."""
        build_dir = tmp_path / "build"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            result = run_build(
                profile=minimal_profile,
                imagebuilder_root=valid_imagebuilder,
                build_dir=build_dir,
            )

            log_content = result.log_path.read_text()
            assert "Command:" in log_content
            assert "make image" in log_content

    def test_with_files_dir(self, minimal_profile, valid_imagebuilder, tmp_path):
        """Should pass files_dir to command."""
        build_dir = tmp_path / "build"
        files_dir = tmp_path / "files"
        files_dir.mkdir()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            run_build(
                profile=minimal_profile,
                imagebuilder_root=valid_imagebuilder,
                build_dir=build_dir,
                files_dir=files_dir,
            )

            # Check command includes FILES
            call_args = mock_run.call_args
            cmd = call_args[0][0]
            assert any(f"FILES={files_dir}" in str(c) for c in cmd)

    def test_with_extra_packages(self, minimal_profile, valid_imagebuilder, tmp_path):
        """Should include extra packages in command."""
        build_dir = tmp_path / "build"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            run_build(
                profile=minimal_profile,
                imagebuilder_root=valid_imagebuilder,
                build_dir=build_dir,
                extra_packages=["tcpdump"],
            )

            call_args = mock_run.call_args
            cmd = call_args[0][0]
            packages_arg = [c for c in cmd if str(c).startswith("PACKAGES=")]
            assert len(packages_arg) == 1
            assert "tcpdump" in packages_arg[0]
