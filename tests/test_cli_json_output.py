"""Tests for CLI JSON output functionality.

These tests verify that CLI commands produce correct JSON output
when the --json flag is used. JSON output must have stable keys
as specified in docs/FRONTENDS.md.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from openwrt_imagegen.cli import app

runner = CliRunner()


@pytest.fixture
def temp_db_url() -> str:
    """Create a temporary database URL for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield f"sqlite:///{tmpdir}/test.db"


@pytest.fixture
def mock_settings(temp_db_url: str) -> MagicMock:
    """Create mock settings with temporary database."""
    settings = MagicMock()
    settings.db_url = temp_db_url
    settings.cache_dir = Path(tempfile.mkdtemp())
    settings.artifacts_dir = Path(tempfile.mkdtemp())
    settings.offline = False
    settings.verification_mode = "full-hash"
    settings.max_concurrent_downloads = 2
    settings.max_concurrent_builds = 2
    settings.download_timeout = 3600
    settings.build_timeout = 3600
    settings.flash_timeout = 1800
    settings.log_level = "INFO"
    settings.tmp_dir = None
    return settings


class TestProfilesJSONOutput:
    """Test JSON output for profiles commands."""

    def test_profiles_list_empty_json(self) -> None:
        """profiles list --json should return [] when no profiles."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_url = f"sqlite:///{tmpdir}/test.db"
            with patch.dict("os.environ", {"OWRT_IMG_DB_URL": db_url}):
                result = runner.invoke(app, ["profiles", "list", "--json"])
                assert result.exit_code == 0
                data = json.loads(result.stdout)
                assert data == []

    def test_profiles_list_with_data_json(self, tmp_path: Path) -> None:
        """profiles list --json should return profile data."""
        db_url = f"sqlite:///{tmp_path}/test.db"

        # Create a profile file
        profile_yaml = tmp_path / "test.yaml"
        profile_yaml.write_text("""
profile_id: test.profile.1
name: Test Profile
device_id: test-device
openwrt_release: "23.05.2"
target: ath79
subtarget: generic
imagebuilder_profile: tplink_archer-c6-v3
tags:
  - test
  - json
""")

        with patch.dict("os.environ", {"OWRT_IMG_DB_URL": db_url}):
            # Import the profile
            runner.invoke(app, ["profiles", "import", str(profile_yaml)])

            # List with JSON output
            result = runner.invoke(app, ["profiles", "list", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.stdout)
            assert isinstance(data, list)
            assert len(data) == 1
            profile = data[0]
            assert profile["profile_id"] == "test.profile.1"
            assert profile["name"] == "Test Profile"
            assert profile["device_id"] == "test-device"
            assert profile["openwrt_release"] == "23.05.2"
            assert profile["target"] == "ath79"
            assert profile["subtarget"] == "generic"
            assert profile["imagebuilder_profile"] == "tplink_archer-c6-v3"
            assert "test" in profile["tags"]
            assert "json" in profile["tags"]

    def test_profiles_show_json(self, tmp_path: Path) -> None:
        """profiles show --json should return profile details."""
        db_url = f"sqlite:///{tmp_path}/test.db"

        # Create a profile file
        profile_yaml = tmp_path / "test.yaml"
        profile_yaml.write_text("""
profile_id: test.show.profile
name: Show Test Profile
device_id: show-device
openwrt_release: "23.05.2"
target: ramips
subtarget: mt7621
imagebuilder_profile: xiaomi_mi-router-4a-gigabit
packages:
  - luci
  - htop
""")

        with patch.dict("os.environ", {"OWRT_IMG_DB_URL": db_url}):
            # Import the profile
            runner.invoke(app, ["profiles", "import", str(profile_yaml)])

            # Show with JSON output
            result = runner.invoke(
                app, ["profiles", "show", "test.show.profile", "--json"]
            )
            assert result.exit_code == 0
            data = json.loads(result.stdout)
            assert data["profile_id"] == "test.show.profile"
            assert data["name"] == "Show Test Profile"
            assert data["packages"] == ["luci", "htop"]

    def test_profiles_show_not_found_json(self, tmp_path: Path) -> None:
        """profiles show --json should fail properly for missing profile."""
        db_url = f"sqlite:///{tmp_path}/test.db"

        with patch.dict("os.environ", {"OWRT_IMG_DB_URL": db_url}):
            result = runner.invoke(
                app, ["profiles", "show", "nonexistent.profile", "--json"]
            )
            assert result.exit_code == 1
            assert "not found" in result.stdout.lower()

    def test_profiles_list_with_filter_json(self, tmp_path: Path) -> None:
        """profiles list --json with filters should return matching profiles."""
        db_url = f"sqlite:///{tmp_path}/test.db"

        # Create profile files
        profile1 = tmp_path / "profile1.yaml"
        profile1.write_text("""
profile_id: test.filter.1
name: Filter Test Profile 1
device_id: filter-device
openwrt_release: "23.05.2"
target: ath79
subtarget: generic
imagebuilder_profile: tplink_archer-c6-v3
tags:
  - test
  - wifi
""")
        profile2 = tmp_path / "profile2.yaml"
        profile2.write_text("""
profile_id: test.filter.2
name: Filter Test Profile 2
device_id: other-device
openwrt_release: "22.03.5"
target: ramips
subtarget: mt7621
imagebuilder_profile: xiaomi_mi-router-4a-gigabit
tags:
  - test
  - router
""")

        with patch.dict("os.environ", {"OWRT_IMG_DB_URL": db_url}):
            # Import profiles
            runner.invoke(app, ["profiles", "import", str(profile1)])
            runner.invoke(app, ["profiles", "import", str(profile2)])

            # Filter by target
            result = runner.invoke(
                app, ["profiles", "list", "--target", "ath79", "--json"]
            )
            assert result.exit_code == 0
            data = json.loads(result.stdout)
            assert len(data) == 1
            assert data[0]["profile_id"] == "test.filter.1"

            # Filter by release
            result = runner.invoke(
                app, ["profiles", "list", "--release", "22.03.5", "--json"]
            )
            assert result.exit_code == 0
            data = json.loads(result.stdout)
            assert len(data) == 1
            assert data[0]["profile_id"] == "test.filter.2"

            # Filter by device ID
            result = runner.invoke(
                app, ["profiles", "list", "--device", "filter-device", "--json"]
            )
            assert result.exit_code == 0
            data = json.loads(result.stdout)
            assert len(data) == 1
            assert data[0]["profile_id"] == "test.filter.1"

            # Filter by subtarget
            result = runner.invoke(
                app, ["profiles", "list", "--subtarget", "mt7621", "--json"]
            )
            assert result.exit_code == 0
            data = json.loads(result.stdout)
            assert len(data) == 1
            assert data[0]["profile_id"] == "test.filter.2"

            # No matches
            result = runner.invoke(
                app, ["profiles", "list", "--target", "x86", "--json"]
            )
            assert result.exit_code == 0
            data = json.loads(result.stdout)
            assert data == []


class TestBuildersJSONOutput:
    """Test JSON output for builders commands."""

    def test_builders_list_empty_json(self, tmp_path: Path) -> None:
        """builders list --json should return [] when no builders."""
        db_url = f"sqlite:///{tmp_path}/test.db"

        with patch.dict("os.environ", {"OWRT_IMG_DB_URL": db_url}):
            result = runner.invoke(app, ["builders", "list", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.stdout)
            assert data == []

    def test_builders_info_json(self, tmp_path: Path) -> None:
        """builders info --json should return cache information."""
        db_url = f"sqlite:///{tmp_path}/test.db"
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()

        with patch.dict(
            "os.environ",
            {"OWRT_IMG_DB_URL": db_url, "OWRT_IMG_CACHE_DIR": str(cache_dir)},
        ):
            result = runner.invoke(app, ["builders", "info", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.stdout)
            assert "cache_dir" in data
            assert "exists" in data
            assert "total_size_human" in data

    def test_builders_prune_dry_run_json(self, tmp_path: Path) -> None:
        """builders prune --dry-run --json should return pruned list."""
        db_url = f"sqlite:///{tmp_path}/test.db"

        with patch.dict("os.environ", {"OWRT_IMG_DB_URL": db_url}):
            result = runner.invoke(app, ["builders", "prune", "--dry-run", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.stdout)
            assert "dry_run" in data
            assert data["dry_run"] is True
            assert "pruned" in data
            assert isinstance(data["pruned"], list)


class TestBuildsJSONOutput:
    """Test JSON output for builds commands."""

    def test_builds_list_empty_json(self, tmp_path: Path) -> None:
        """builds list --json should return [] when no builds."""
        db_url = f"sqlite:///{tmp_path}/test.db"

        with patch.dict("os.environ", {"OWRT_IMG_DB_URL": db_url}):
            result = runner.invoke(app, ["build", "list", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.stdout)
            assert data == []

    def test_builds_batch_no_filter_error(self, tmp_path: Path) -> None:
        """builds batch should fail without filters."""
        db_url = f"sqlite:///{tmp_path}/test.db"

        with patch.dict("os.environ", {"OWRT_IMG_DB_URL": db_url}):
            result = runner.invoke(app, ["build", "batch"])
            assert result.exit_code == 1
            assert "at least one filter" in result.stdout.lower()

    def test_builds_batch_invalid_mode(self, tmp_path: Path) -> None:
        """builds batch with invalid mode should fail."""
        db_url = f"sqlite:///{tmp_path}/test.db"

        with patch.dict("os.environ", {"OWRT_IMG_DB_URL": db_url}):
            result = runner.invoke(
                app,
                ["build", "batch", "--profile", "test", "--mode", "invalid"],
            )
            assert result.exit_code == 1
            assert "invalid mode" in result.stdout.lower()

    def test_builds_batch_json_output_structure(self, tmp_path: Path) -> None:
        """builds batch --json should return proper structure."""
        db_url = f"sqlite:///{tmp_path}/test.db"

        # Create a profile for the batch build
        profile_yaml = tmp_path / "test.yaml"
        profile_yaml.write_text("""
profile_id: batch.test.profile
name: Batch Test Profile
device_id: batch-device
openwrt_release: "23.05.2"
target: ath79
subtarget: generic
imagebuilder_profile: tplink_archer-c6-v3
""")

        with patch.dict("os.environ", {"OWRT_IMG_DB_URL": db_url}):
            # Import the profile
            runner.invoke(app, ["profiles", "import", str(profile_yaml)])

            # Mock the ensure_builder in imagebuilder.service module
            with patch(
                "openwrt_imagegen.imagebuilder.service.ensure_builder"
            ) as mock_ensure:
                mock_ensure.side_effect = Exception(
                    "Mocked - Image Builder not available"
                )

                result = runner.invoke(
                    app,
                    [
                        "build",
                        "batch",
                        "--profile",
                        "batch.test.profile",
                        "--json",
                    ],
                )

                # Should complete (possibly with failures)
                data = json.loads(result.stdout)
                assert "total" in data
                assert "succeeded" in data
                assert "failed" in data
                assert "cache_hits" in data
                assert "mode" in data
                assert "results" in data
                assert isinstance(data["results"], list)


class TestArtifactsJSONOutput:
    """Test JSON output for artifacts commands."""

    def test_artifacts_list_empty_json(self, tmp_path: Path) -> None:
        """artifacts list --json should return [] when no artifacts."""
        db_url = f"sqlite:///{tmp_path}/test.db"

        with patch.dict("os.environ", {"OWRT_IMG_DB_URL": db_url}):
            result = runner.invoke(app, ["artifacts", "list", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.stdout)
            assert data == []

    def test_artifacts_show_not_found_json(self, tmp_path: Path) -> None:
        """artifacts show should fail properly for missing artifact."""
        db_url = f"sqlite:///{tmp_path}/test.db"

        with patch.dict("os.environ", {"OWRT_IMG_DB_URL": db_url}):
            result = runner.invoke(app, ["artifacts", "show", "999", "--json"])
            assert result.exit_code == 1
            assert "not found" in result.stdout.lower()


class TestFlashJSONOutput:
    """Test JSON output for flash commands.

    These tests use mocked devices and artifacts to avoid real flashing.
    """

    def test_flash_write_requires_artifact(self, tmp_path: Path) -> None:
        """flash write should fail with proper error for missing artifact."""
        db_url = f"sqlite:///{tmp_path}/test.db"

        with patch.dict("os.environ", {"OWRT_IMG_DB_URL": db_url}):
            result = runner.invoke(
                app,
                ["flash", "write", "999", "/dev/sda", "--dry-run", "--force"],
            )
            assert result.exit_code == 1
            assert "not found" in result.stdout.lower()

    def test_flash_image_dry_run_json(self, tmp_path: Path) -> None:
        """flash image --dry-run --json should return proper structure."""
        # Create a fake image file
        image_file = tmp_path / "test-image.bin"
        image_file.write_bytes(b"\x00" * 1024)

        # Mock device validation in flash.device module
        with patch("openwrt_imagegen.flash.device.validate_device") as mock_validate:
            mock_device_info = MagicMock()
            mock_device_info.path = "/dev/sdb"
            mock_device_info.model = "Test Device"
            mock_device_info.serial = "12345"
            mock_device_info.size = 1024 * 1024 * 1024  # 1GB
            mock_validate.return_value = mock_device_info

            # Also need to mock at service level since that's where it's called
            with patch(
                "openwrt_imagegen.flash.service.validate_device"
            ) as mock_service_validate:
                mock_service_validate.return_value = mock_device_info

                result = runner.invoke(
                    app,
                    [
                        "flash",
                        "image",
                        str(image_file),
                        "/dev/sdb",
                        "--dry-run",
                        "--force",
                        "--json",
                    ],
                )

                assert result.exit_code == 0, f"Unexpected output: {result.stdout}"
                data = json.loads(result.stdout)
                assert "success" in data
                assert data["success"] is True
                assert "image_path" in data
                assert "device_path" in data
                assert "bytes_written" in data
                assert "verification_mode" in data
                assert "verification_result" in data

    def test_flash_image_missing_file_json(self) -> None:
        """flash image with missing file should return error."""
        result = runner.invoke(
            app,
            [
                "flash",
                "image",
                "/nonexistent/image.bin",
                "/dev/sdb",
                "--dry-run",
                "--force",
                "--json",
            ],
        )
        # Should fail due to missing image file
        assert result.exit_code == 1

    def test_flash_list_empty_json(self, tmp_path: Path) -> None:
        """flash list --json should return [] when no flash records."""
        db_url = f"sqlite:///{tmp_path}/test.db"

        with patch.dict("os.environ", {"OWRT_IMG_DB_URL": db_url}):
            result = runner.invoke(app, ["flash", "list", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.stdout)
            assert data == []

    def test_flash_list_invalid_status(self, tmp_path: Path) -> None:
        """flash list with invalid status should fail."""
        db_url = f"sqlite:///{tmp_path}/test.db"

        with patch.dict("os.environ", {"OWRT_IMG_DB_URL": db_url}):
            result = runner.invoke(
                app, ["flash", "list", "--status", "invalid", "--json"]
            )
            assert result.exit_code == 1
            assert "invalid status" in result.stdout.lower()


class TestJSONOutputConsistency:
    """Test that JSON outputs are consistent and parseable."""

    def test_config_json_parseable(self) -> None:
        """config --json output must be valid JSON."""
        result = runner.invoke(app, ["config", "--json"])
        assert result.exit_code == 0
        # Should be valid JSON
        data = json.loads(result.stdout)
        assert isinstance(data, dict)

    def test_profiles_list_json_always_array(self, tmp_path: Path) -> None:
        """profiles list --json must always return an array."""
        db_url = f"sqlite:///{tmp_path}/test.db"

        with patch.dict("os.environ", {"OWRT_IMG_DB_URL": db_url}):
            result = runner.invoke(app, ["profiles", "list", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.stdout)
            assert isinstance(data, list)

    def test_builders_list_json_always_array(self, tmp_path: Path) -> None:
        """builders list --json must always return an array."""
        db_url = f"sqlite:///{tmp_path}/test.db"

        with patch.dict("os.environ", {"OWRT_IMG_DB_URL": db_url}):
            result = runner.invoke(app, ["builders", "list", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.stdout)
            assert isinstance(data, list)

    def test_builds_list_json_always_array(self, tmp_path: Path) -> None:
        """builds list --json must always return an array."""
        db_url = f"sqlite:///{tmp_path}/test.db"

        with patch.dict("os.environ", {"OWRT_IMG_DB_URL": db_url}):
            result = runner.invoke(app, ["build", "list", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.stdout)
            assert isinstance(data, list)

    def test_artifacts_list_json_always_array(self, tmp_path: Path) -> None:
        """artifacts list --json must always return an array."""
        db_url = f"sqlite:///{tmp_path}/test.db"

        with patch.dict("os.environ", {"OWRT_IMG_DB_URL": db_url}):
            result = runner.invoke(app, ["artifacts", "list", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.stdout)
            assert isinstance(data, list)

    def test_flash_list_json_always_array(self, tmp_path: Path) -> None:
        """flash list --json must always return an array."""
        db_url = f"sqlite:///{tmp_path}/test.db"

        with patch.dict("os.environ", {"OWRT_IMG_DB_URL": db_url}):
            result = runner.invoke(app, ["flash", "list", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.stdout)
            assert isinstance(data, list)


class TestJSONOutputStableKeys:
    """Test that JSON outputs have stable keys as per FRONTENDS.md."""

    def test_flash_result_has_required_keys(self, tmp_path: Path) -> None:
        """flash image --json result should have required keys."""
        # Create a fake image file
        image_file = tmp_path / "test-image.bin"
        image_file.write_bytes(b"\x00" * 1024)

        # Mock device validation in flash.device module
        with patch("openwrt_imagegen.flash.device.validate_device") as mock_validate:
            mock_device_info = MagicMock()
            mock_device_info.path = "/dev/sdb"
            mock_device_info.model = "Test Device"
            mock_device_info.serial = "12345"
            mock_device_info.size = 1024 * 1024 * 1024
            mock_validate.return_value = mock_device_info

            # Also need to mock at service level
            with patch(
                "openwrt_imagegen.flash.service.validate_device"
            ) as mock_service_validate:
                mock_service_validate.return_value = mock_device_info

                result = runner.invoke(
                    app,
                    [
                        "flash",
                        "image",
                        str(image_file),
                        "/dev/sdb",
                        "--dry-run",
                        "--force",
                        "--json",
                    ],
                )

                assert result.exit_code == 0, f"Unexpected output: {result.stdout}"
                data = json.loads(result.stdout)

                # Check required keys per FRONTENDS.md
                required_keys = [
                    "success",
                    "image_path",
                    "device_path",
                    "bytes_written",
                    "source_hash",
                    "verification_mode",
                    "verification_result",
                ]
                for key in required_keys:
                    assert key in data, f"Missing required key: {key}"

    def test_batch_build_result_has_required_keys(self, tmp_path: Path) -> None:
        """batch build --json result should have required keys."""
        db_url = f"sqlite:///{tmp_path}/test.db"

        # Create a profile
        profile_yaml = tmp_path / "test.yaml"
        profile_yaml.write_text("""
profile_id: keys.test.profile
name: Keys Test Profile
device_id: keys-device
openwrt_release: "23.05.2"
target: ath79
subtarget: generic
imagebuilder_profile: tplink_archer-c6-v3
""")

        with patch.dict("os.environ", {"OWRT_IMG_DB_URL": db_url}):
            runner.invoke(app, ["profiles", "import", str(profile_yaml)])

            with patch(
                "openwrt_imagegen.imagebuilder.service.ensure_builder"
            ) as mock_ensure:
                mock_ensure.side_effect = Exception("Mocked")

                result = runner.invoke(
                    app,
                    [
                        "build",
                        "batch",
                        "--profile",
                        "keys.test.profile",
                        "--json",
                    ],
                )

                data = json.loads(result.stdout)

                # Check required keys per FRONTENDS.md
                required_keys = [
                    "total",
                    "succeeded",
                    "failed",
                    "cache_hits",
                    "mode",
                    "results",
                ]
                for key in required_keys:
                    assert key in data, f"Missing required key: {key}"

                # Check per-profile result structure
                if data["results"]:
                    result_item = data["results"][0]
                    per_profile_keys = [
                        "profile_id",
                        "success",
                    ]
                    for key in per_profile_keys:
                        assert key in result_item, f"Missing per-profile key: {key}"
