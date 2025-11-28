"""Tests for profile import/export IO operations.

These tests verify loading and saving profiles from/to YAML and JSON files.
"""

import json
from pathlib import Path

import pytest
import yaml

from openwrt_imagegen.profiles.io import (
    export_profile,
    export_profile_to_json,
    export_profile_to_yaml,
    load_profile,
    load_profile_from_json,
    load_profile_from_yaml,
    load_profiles_from_directory,
    profile_to_json_string,
    profile_to_yaml_string,
)
from openwrt_imagegen.profiles.schema import ProfileSchema


@pytest.fixture
def minimal_profile_data():
    """Return minimal valid profile data."""
    return {
        "profile_id": "test.device.io",
        "name": "IO Test Profile",
        "device_id": "test-device",
        "openwrt_release": "23.05.3",
        "target": "ath79",
        "subtarget": "generic",
        "imagebuilder_profile": "tplink_test",
    }


@pytest.fixture
def full_profile_data():
    """Return full valid profile data."""
    return {
        "profile_id": "test.device.full",
        "name": "Full Test Profile",
        "description": "A complete test profile for IO testing",
        "device_id": "test-device-full",
        "tags": ["test", "io", "example"],
        "openwrt_release": "23.05.3",
        "target": "ath79",
        "subtarget": "generic",
        "imagebuilder_profile": "tplink_test",
        "packages": ["luci", "htop"],
        "packages_remove": ["ppp"],
        "files": [
            {
                "source": "test/banner",
                "destination": "/etc/banner",
                "mode": "0644",
            }
        ],
        "policies": {
            "filesystem": "squashfs",
            "strip_debug": True,
        },
        "build_defaults": {
            "rebuild_if_cached": False,
        },
    }


class TestLoadYAML:
    """Test YAML loading functionality."""

    def test_load_valid_yaml(self, tmp_path, minimal_profile_data):
        """Should load valid YAML file."""
        yaml_path = tmp_path / "test.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(minimal_profile_data, f)

        profile = load_profile_from_yaml(yaml_path)
        assert profile.profile_id == "test.device.io"
        assert profile.name == "IO Test Profile"

    def test_load_yaml_file_not_found(self, tmp_path):
        """Should raise FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            load_profile_from_yaml(tmp_path / "nonexistent.yaml")

    def test_load_invalid_yaml(self, tmp_path):
        """Should raise error for invalid YAML."""
        yaml_path = tmp_path / "invalid.yaml"
        with open(yaml_path, "w") as f:
            f.write("invalid: yaml: content: [")

        with pytest.raises(yaml.YAMLError):
            load_profile_from_yaml(yaml_path)

    def test_load_yaml_not_mapping(self, tmp_path):
        """Should raise error if YAML is not a mapping."""
        yaml_path = tmp_path / "list.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(["item1", "item2"], f)

        with pytest.raises(ValueError) as exc_info:
            load_profile_from_yaml(yaml_path)
        assert "Expected a YAML mapping" in str(exc_info.value)


class TestLoadJSON:
    """Test JSON loading functionality."""

    def test_load_valid_json(self, tmp_path, minimal_profile_data):
        """Should load valid JSON file."""
        json_path = tmp_path / "test.json"
        with open(json_path, "w") as f:
            json.dump(minimal_profile_data, f)

        profile = load_profile_from_json(json_path)
        assert profile.profile_id == "test.device.io"

    def test_load_json_file_not_found(self, tmp_path):
        """Should raise FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            load_profile_from_json(tmp_path / "nonexistent.json")

    def test_load_invalid_json(self, tmp_path):
        """Should raise error for invalid JSON."""
        json_path = tmp_path / "invalid.json"
        with open(json_path, "w") as f:
            f.write("{invalid json}")

        with pytest.raises(json.JSONDecodeError):
            load_profile_from_json(json_path)

    def test_load_json_not_object(self, tmp_path):
        """Should raise error if JSON is not an object."""
        json_path = tmp_path / "list.json"
        with open(json_path, "w") as f:
            json.dump(["item1", "item2"], f)

        with pytest.raises(ValueError) as exc_info:
            load_profile_from_json(json_path)
        assert "Expected a JSON object" in str(exc_info.value)


class TestLoadProfile:
    """Test unified profile loading by extension."""

    def test_load_yaml_extension(self, tmp_path, minimal_profile_data):
        """Should load .yaml file correctly."""
        yaml_path = tmp_path / "test.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(minimal_profile_data, f)

        profile = load_profile(yaml_path)
        assert profile.profile_id == "test.device.io"

    def test_load_yml_extension(self, tmp_path, minimal_profile_data):
        """Should load .yml file correctly."""
        yml_path = tmp_path / "test.yml"
        with open(yml_path, "w") as f:
            yaml.dump(minimal_profile_data, f)

        profile = load_profile(yml_path)
        assert profile.profile_id == "test.device.io"

    def test_load_json_extension(self, tmp_path, minimal_profile_data):
        """Should load .json file correctly."""
        json_path = tmp_path / "test.json"
        with open(json_path, "w") as f:
            json.dump(minimal_profile_data, f)

        profile = load_profile(json_path)
        assert profile.profile_id == "test.device.io"

    def test_unsupported_extension(self, tmp_path):
        """Should raise error for unsupported extension."""
        txt_path = tmp_path / "test.txt"
        txt_path.touch()

        with pytest.raises(ValueError) as exc_info:
            load_profile(txt_path)
        assert "Unsupported file extension" in str(exc_info.value)

    def test_validation_error_on_invalid_data(self, tmp_path):
        """Should raise ValidationError for invalid profile data."""
        yaml_path = tmp_path / "invalid.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump({"name": "Missing required fields"}, f)

        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            load_profile(yaml_path)


class TestExportProfile:
    """Test profile export functionality."""

    @pytest.fixture
    def sample_profile(self, full_profile_data):
        """Create a sample ProfileSchema for export tests."""
        return ProfileSchema.model_validate(full_profile_data)

    def test_export_to_yaml(self, tmp_path, sample_profile):
        """Should export profile to YAML file."""
        yaml_path = tmp_path / "exported.yaml"
        export_profile_to_yaml(sample_profile, yaml_path)

        assert yaml_path.exists()

        # Verify content can be read back
        loaded = load_profile_from_yaml(yaml_path)
        assert loaded.profile_id == sample_profile.profile_id
        assert loaded.packages == sample_profile.packages

    def test_export_to_json(self, tmp_path, sample_profile):
        """Should export profile to JSON file."""
        json_path = tmp_path / "exported.json"
        export_profile_to_json(sample_profile, json_path)

        assert json_path.exists()

        # Verify content can be read back
        loaded = load_profile_from_json(json_path)
        assert loaded.profile_id == sample_profile.profile_id
        assert loaded.packages == sample_profile.packages

    def test_export_profile_by_extension(self, tmp_path, sample_profile):
        """Should export based on file extension."""
        yaml_path = tmp_path / "test.yaml"
        json_path = tmp_path / "test.json"

        export_profile(sample_profile, yaml_path)
        export_profile(sample_profile, json_path)

        assert yaml_path.exists()
        assert json_path.exists()

    def test_export_unsupported_extension(self, tmp_path, sample_profile):
        """Should raise error for unsupported extension."""
        txt_path = tmp_path / "test.txt"

        with pytest.raises(ValueError) as exc_info:
            export_profile(sample_profile, txt_path)
        assert "Unsupported file extension" in str(exc_info.value)

    def test_export_excludes_none(self, tmp_path, minimal_profile_data):
        """Should exclude None values from export."""
        profile = ProfileSchema.model_validate(minimal_profile_data)
        yaml_path = tmp_path / "minimal.yaml"
        export_profile_to_yaml(profile, yaml_path)

        with open(yaml_path) as f:
            data = yaml.safe_load(f)

        # Optional fields should not be present
        assert "description" not in data
        assert "packages" not in data


class TestProfileToString:
    """Test profile to string conversion."""

    @pytest.fixture
    def sample_profile(self, full_profile_data):
        """Create a sample ProfileSchema."""
        return ProfileSchema.model_validate(full_profile_data)

    def test_to_yaml_string(self, sample_profile):
        """Should convert profile to YAML string."""
        yaml_str = profile_to_yaml_string(sample_profile)
        assert isinstance(yaml_str, str)

        # Should be valid YAML
        data = yaml.safe_load(yaml_str)
        assert data["profile_id"] == sample_profile.profile_id

    def test_to_json_string(self, sample_profile):
        """Should convert profile to JSON string."""
        json_str = profile_to_json_string(sample_profile)
        assert isinstance(json_str, str)

        # Should be valid JSON
        data = json.loads(json_str)
        assert data["profile_id"] == sample_profile.profile_id


class TestLoadProfilesFromDirectory:
    """Test bulk profile loading from directory."""

    def test_load_from_directory(self, tmp_path, minimal_profile_data):
        """Should load all matching profiles from directory."""
        # Create multiple profile files
        for i in range(3):
            data = minimal_profile_data.copy()
            data["profile_id"] = f"test.profile.{i}"
            data["name"] = f"Test Profile {i}"
            path = tmp_path / f"profile{i}.yaml"
            with open(path, "w") as f:
                yaml.dump(data, f)

        result = load_profiles_from_directory(tmp_path)

        assert result.total == 3
        assert result.succeeded == 3
        assert result.failed == 0
        assert len(result.results) == 3
        assert all(r.success for r in result.results)

    def test_load_with_pattern(self, tmp_path, minimal_profile_data):
        """Should only load files matching pattern."""
        # Create YAML and JSON files
        yaml_data = minimal_profile_data.copy()
        yaml_data["profile_id"] = "yaml.profile"
        with open(tmp_path / "profile.yaml", "w") as f:
            yaml.dump(yaml_data, f)

        json_data = minimal_profile_data.copy()
        json_data["profile_id"] = "json.profile"
        with open(tmp_path / "profile.json", "w") as f:
            json.dump(json_data, f)

        # Load only YAML files
        result = load_profiles_from_directory(tmp_path, pattern="*.yaml")
        assert result.total == 1
        assert result.results[0].profile_id == "yaml.profile"

        # Load only JSON files
        result = load_profiles_from_directory(tmp_path, pattern="*.json")
        assert result.total == 1
        assert result.results[0].profile_id == "json.profile"

    def test_load_with_validation_errors(self, tmp_path, minimal_profile_data):
        """Should report validation errors without failing entire batch."""
        # Create one valid file
        with open(tmp_path / "valid.yaml", "w") as f:
            yaml.dump(minimal_profile_data, f)

        # Create one invalid file
        with open(tmp_path / "invalid.yaml", "w") as f:
            yaml.dump({"name": "Missing fields"}, f)

        result = load_profiles_from_directory(tmp_path)

        assert result.total == 2
        assert result.succeeded == 1
        assert result.failed == 1

        # Check individual results
        valid_result = next(r for r in result.results if r.success)
        invalid_result = next(r for r in result.results if not r.success)

        assert valid_result.profile_id == "test.device.io"
        assert "Validation error" in (invalid_result.error or "")

    def test_load_empty_directory(self, tmp_path):
        """Should handle empty directory."""
        result = load_profiles_from_directory(tmp_path)

        assert result.total == 0
        assert result.succeeded == 0
        assert result.failed == 0

    def test_load_nonexistent_directory(self, tmp_path):
        """Should raise error for nonexistent directory."""
        with pytest.raises(FileNotFoundError):
            load_profiles_from_directory(tmp_path / "nonexistent")


class TestRoundTrip:
    """Test that export/import round-trips preserve data."""

    @pytest.fixture
    def full_profile(self, full_profile_data):
        """Create a full profile for round-trip tests."""
        return ProfileSchema.model_validate(full_profile_data)

    def test_yaml_round_trip(self, tmp_path, full_profile):
        """Should preserve profile data through YAML round-trip."""
        yaml_path = tmp_path / "roundtrip.yaml"

        export_profile_to_yaml(full_profile, yaml_path)
        loaded = load_profile_from_yaml(yaml_path)

        assert loaded.profile_id == full_profile.profile_id
        assert loaded.name == full_profile.name
        assert loaded.packages == full_profile.packages
        assert loaded.packages_remove == full_profile.packages_remove
        assert loaded.tags == full_profile.tags
        assert loaded.policies is not None
        assert loaded.policies.filesystem == "squashfs"

    def test_json_round_trip(self, tmp_path, full_profile):
        """Should preserve profile data through JSON round-trip."""
        json_path = tmp_path / "roundtrip.json"

        export_profile_to_json(full_profile, json_path)
        loaded = load_profile_from_json(json_path)

        assert loaded.profile_id == full_profile.profile_id
        assert loaded.name == full_profile.name
        assert loaded.packages == full_profile.packages
        assert loaded.files is not None
        assert len(loaded.files) == 1
        assert loaded.files[0].destination == "/etc/banner"


class TestLoadRealProfiles:
    """Test loading the actual sample profiles from the repository."""

    @pytest.fixture
    def profiles_dir(self):
        """Return the path to the profiles directory."""
        # Find repo root relative to tests
        repo_root = Path(__file__).parent.parent
        profiles_dir = repo_root / "profiles"
        if profiles_dir.exists():
            return profiles_dir
        pytest.skip("Profiles directory not found")

    def test_load_home_ap_livingroom(self, profiles_dir):
        """Should load home-ap-livingroom.yaml profile."""
        profile = load_profile(profiles_dir / "home-ap-livingroom.yaml")

        assert profile.profile_id == "home.ap-livingroom.23.05"
        assert profile.target == "ath79"
        assert profile.subtarget == "generic"
        assert profile.packages is not None
        assert "luci" in profile.packages

    def test_load_lab_router_snapshot(self, profiles_dir):
        """Should load lab-router1-snapshot.yaml profile."""
        profile = load_profile(profiles_dir / "lab-router1-snapshot.yaml")

        assert profile.profile_id == "lab.router1.snapshot"
        assert profile.openwrt_release == "snapshot"
        assert profile.policies is not None
        assert profile.policies.allow_snapshot is True

        # Snapshot validation should pass
        profile.validate_snapshot_policy()

    def test_load_all_profiles(self, profiles_dir):
        """Should load all sample profiles from directory."""
        result = load_profiles_from_directory(profiles_dir)

        # Should have at least 3 sample profiles
        assert result.total >= 3
        assert result.failed == 0, (
            f"Failed profiles: {[r.error for r in result.results if not r.success]}"
        )
