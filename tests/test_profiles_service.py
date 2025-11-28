"""Tests for profile service CRUD and query operations.

These tests verify the profile service layer that handles database
operations for profiles.
"""

import json

import pytest
import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from openwrt_imagegen.db import Base
from openwrt_imagegen.profiles.schema import ProfileSchema
from openwrt_imagegen.profiles.service import (
    ProfileExistsError,
    ProfileNotFoundError,
    create_or_update_profile,
    create_profile,
    delete_profile,
    export_profile_to_file,
    export_profiles_to_directory,
    get_profile,
    get_profile_or_none,
    import_profile_from_file,
    import_profiles_from_directory,
    list_profiles,
    profile_to_schema,
    query_profiles,
    schema_to_profile,
    update_profile,
    validate_profile_data,
)


@pytest.fixture
def engine():
    """Create an in-memory SQLite engine for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture
def session_factory(engine):
    """Create a session factory for testing."""
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def session(session_factory):
    """Create a session for testing."""
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def minimal_profile_data():
    """Return minimal valid profile data."""
    return {
        "profile_id": "test.service.profile",
        "name": "Service Test Profile",
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
        "profile_id": "test.service.full",
        "name": "Full Service Test Profile",
        "description": "A complete test profile",
        "device_id": "test-device-full",
        "tags": ["test", "service", "full"],
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
        "notes": "Test notes",
    }


class TestProfileConversion:
    """Test conversion between ORM models and schemas."""

    def test_schema_to_profile(self, minimal_profile_data):
        """Should convert schema to ORM model."""
        schema = ProfileSchema.model_validate(minimal_profile_data)
        profile = schema_to_profile(schema)

        assert profile.profile_id == "test.service.profile"
        assert profile.name == "Service Test Profile"
        assert profile.device_id == "test-device"
        assert profile.openwrt_release == "23.05.3"

    def test_schema_to_profile_full(self, full_profile_data):
        """Should convert full schema to ORM model."""
        schema = ProfileSchema.model_validate(full_profile_data)
        profile = schema_to_profile(schema)

        assert profile.profile_id == "test.service.full"
        assert profile.packages == ["luci", "htop"]
        assert profile.files is not None
        assert len(profile.files) == 1
        assert profile.policies is not None
        assert profile.policies["filesystem"] == "squashfs"

    def test_profile_to_schema(self, session, full_profile_data):
        """Should convert ORM model to schema."""
        # Create profile in DB
        schema = ProfileSchema.model_validate(full_profile_data)
        profile = schema_to_profile(schema)
        session.add(profile)
        session.commit()

        # Convert back to schema
        result_schema = profile_to_schema(profile)

        assert result_schema.profile_id == "test.service.full"
        assert result_schema.packages == ["luci", "htop"]
        assert result_schema.policies is not None
        assert result_schema.policies.filesystem == "squashfs"
        assert result_schema.files is not None
        assert len(result_schema.files) == 1

    def test_profile_to_schema_with_meta(self, session, minimal_profile_data):
        """Should include metadata when requested."""
        schema = ProfileSchema.model_validate(minimal_profile_data)
        profile = schema_to_profile(schema)
        session.add(profile)
        session.commit()

        result_schema = profile_to_schema(profile, include_meta=True)

        assert result_schema.meta is not None
        assert result_schema.meta.created_at is not None


class TestCRUDOperations:
    """Test CRUD operations for profiles."""

    def test_create_profile(self, session, minimal_profile_data):
        """Should create a new profile."""
        schema = ProfileSchema.model_validate(minimal_profile_data)
        profile = create_profile(session, schema)

        assert profile.id is not None
        assert profile.profile_id == "test.service.profile"

    def test_create_profile_exists(self, session, minimal_profile_data):
        """Should raise error when profile already exists."""
        schema = ProfileSchema.model_validate(minimal_profile_data)
        create_profile(session, schema)
        session.commit()

        with pytest.raises(ProfileExistsError) as exc_info:
            create_profile(session, schema)
        assert "test.service.profile" in str(exc_info.value)

    def test_get_profile(self, session, minimal_profile_data):
        """Should get existing profile by profile_id."""
        schema = ProfileSchema.model_validate(minimal_profile_data)
        create_profile(session, schema)
        session.commit()

        profile = get_profile(session, "test.service.profile")
        assert profile.name == "Service Test Profile"

    def test_get_profile_not_found(self, session):
        """Should raise error when profile not found."""
        with pytest.raises(ProfileNotFoundError) as exc_info:
            get_profile(session, "nonexistent")
        assert "nonexistent" in str(exc_info.value)

    def test_get_profile_or_none(self, session, minimal_profile_data):
        """Should return None when profile not found."""
        result = get_profile_or_none(session, "nonexistent")
        assert result is None

        # Create profile and try again
        schema = ProfileSchema.model_validate(minimal_profile_data)
        create_profile(session, schema)
        session.commit()

        result = get_profile_or_none(session, "test.service.profile")
        assert result is not None

    def test_update_profile(self, session, minimal_profile_data):
        """Should update existing profile."""
        schema = ProfileSchema.model_validate(minimal_profile_data)
        create_profile(session, schema)
        session.commit()

        # Update schema
        minimal_profile_data["name"] = "Updated Name"
        minimal_profile_data["packages"] = ["luci", "htop"]
        updated_schema = ProfileSchema.model_validate(minimal_profile_data)

        profile = update_profile(session, "test.service.profile", updated_schema)
        session.commit()

        assert profile.name == "Updated Name"
        assert profile.packages == ["luci", "htop"]

    def test_update_profile_not_found(self, session, minimal_profile_data):
        """Should raise error when updating nonexistent profile."""
        # Use matching profile_id for the nonexistent case
        minimal_profile_data["profile_id"] = "nonexistent"
        schema = ProfileSchema.model_validate(minimal_profile_data)

        with pytest.raises(ProfileNotFoundError):
            update_profile(session, "nonexistent", schema)

    def test_update_profile_id_mismatch(self, session, minimal_profile_data):
        """Should raise error when profile_id doesn't match."""
        schema = ProfileSchema.model_validate(minimal_profile_data)
        create_profile(session, schema)
        session.commit()

        # Try to update with mismatched profile_id
        with pytest.raises(ValueError) as exc_info:
            update_profile(session, "different-id", schema)
        assert "doesn't match" in str(exc_info.value)

    def test_delete_profile(self, session, minimal_profile_data):
        """Should delete existing profile."""
        schema = ProfileSchema.model_validate(minimal_profile_data)
        create_profile(session, schema)
        session.commit()

        delete_profile(session, "test.service.profile")
        session.commit()

        result = get_profile_or_none(session, "test.service.profile")
        assert result is None

    def test_delete_profile_not_found(self, session):
        """Should raise error when deleting nonexistent profile."""
        with pytest.raises(ProfileNotFoundError):
            delete_profile(session, "nonexistent")

    def test_create_or_update_profile_create(self, session, minimal_profile_data):
        """Should create profile when it doesn't exist."""
        schema = ProfileSchema.model_validate(minimal_profile_data)
        profile, created = create_or_update_profile(session, schema)

        assert created is True
        assert profile.profile_id == "test.service.profile"

    def test_create_or_update_profile_update(self, session, minimal_profile_data):
        """Should update profile when it exists."""
        schema = ProfileSchema.model_validate(minimal_profile_data)
        create_profile(session, schema)
        session.commit()

        minimal_profile_data["name"] = "Updated Name"
        updated_schema = ProfileSchema.model_validate(minimal_profile_data)
        profile, created = create_or_update_profile(session, updated_schema)

        assert created is False
        assert profile.name == "Updated Name"


class TestQueryOperations:
    """Test query operations for profiles."""

    @pytest.fixture
    def populated_db(self, session):
        """Create multiple profiles for query tests."""
        profiles_data = [
            {
                "profile_id": "home.device1.23.05",
                "name": "Home Device 1",
                "device_id": "device-1",
                "tags": ["home", "wifi"],
                "openwrt_release": "23.05.3",
                "target": "ath79",
                "subtarget": "generic",
                "imagebuilder_profile": "test1",
            },
            {
                "profile_id": "home.device2.23.05",
                "name": "Home Device 2",
                "device_id": "device-2",
                "tags": ["home", "router"],
                "openwrt_release": "23.05.3",
                "target": "ath79",
                "subtarget": "generic",
                "imagebuilder_profile": "test2",
            },
            {
                "profile_id": "lab.device1.22.03",
                "name": "Lab Device 1",
                "device_id": "device-1",
                "tags": ["lab", "test"],
                "openwrt_release": "22.03.5",
                "target": "ramips",
                "subtarget": "mt7621",
                "imagebuilder_profile": "test3",
            },
        ]

        for data in profiles_data:
            schema = ProfileSchema.model_validate(data)
            profile = schema_to_profile(schema)
            session.add(profile)

        session.commit()

    def test_list_profiles(self, session, populated_db):
        """Should list all profiles."""
        _ = populated_db  # Fixture populates database
        profiles = list_profiles(session)
        assert len(profiles) == 3

    def test_list_profiles_empty(self, session):
        """Should return empty list when no profiles."""
        profiles = list_profiles(session)
        assert len(profiles) == 0

    def test_query_by_device_id(self, session, populated_db):
        """Should query profiles by device_id."""
        _ = populated_db  # Fixture populates database
        profiles = query_profiles(session, device_id="device-1")
        assert len(profiles) == 2

    def test_query_by_release(self, session, populated_db):
        """Should query profiles by openwrt_release."""
        _ = populated_db  # Fixture populates database
        profiles = query_profiles(session, openwrt_release="23.05.3")
        assert len(profiles) == 2

    def test_query_by_target(self, session, populated_db):
        """Should query profiles by target."""
        _ = populated_db  # Fixture populates database
        profiles = query_profiles(session, target="ramips")
        assert len(profiles) == 1

    def test_query_by_subtarget(self, session, populated_db):
        """Should query profiles by subtarget."""
        _ = populated_db  # Fixture populates database
        profiles = query_profiles(session, subtarget="mt7621")
        assert len(profiles) == 1

    def test_query_combined_filters(self, session, populated_db):
        """Should combine multiple filters."""
        _ = populated_db  # Fixture populates database
        profiles = query_profiles(
            session, openwrt_release="23.05.3", target="ath79", subtarget="generic"
        )
        assert len(profiles) == 2

    def test_query_no_matches(self, session, populated_db):
        """Should return empty when no matches."""
        _ = populated_db  # Fixture populates database
        profiles = query_profiles(session, openwrt_release="999.0")
        assert len(profiles) == 0


class TestImportExportOperations:
    """Test import/export operations with database."""

    def test_import_from_yaml(self, session, tmp_path, minimal_profile_data):
        """Should import profile from YAML file."""
        yaml_path = tmp_path / "test.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(minimal_profile_data, f)

        result = import_profile_from_file(session, yaml_path)

        assert result.success is True
        assert result.profile_id == "test.service.profile"
        assert result.created is True

        # Verify in database
        profile = get_profile(session, "test.service.profile")
        assert profile.name == "Service Test Profile"

    def test_import_from_json(self, session, tmp_path, minimal_profile_data):
        """Should import profile from JSON file."""
        json_path = tmp_path / "test.json"
        with open(json_path, "w") as f:
            json.dump(minimal_profile_data, f)

        result = import_profile_from_file(session, json_path)

        assert result.success is True
        assert result.created is True

    def test_import_update_existing(self, session, tmp_path, minimal_profile_data):
        """Should update existing profile when allowed."""
        # Create initial profile
        schema = ProfileSchema.model_validate(minimal_profile_data)
        create_profile(session, schema)
        session.commit()

        # Create file with updated data
        minimal_profile_data["name"] = "Updated Name"
        yaml_path = tmp_path / "test.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(minimal_profile_data, f)

        result = import_profile_from_file(session, yaml_path, update_existing=True)

        assert result.success is True
        assert result.created is False

        profile = get_profile(session, "test.service.profile")
        assert profile.name == "Updated Name"

    def test_import_no_update_existing(self, session, tmp_path, minimal_profile_data):
        """Should fail when profile exists and update not allowed."""
        # Create initial profile
        schema = ProfileSchema.model_validate(minimal_profile_data)
        create_profile(session, schema)
        session.commit()

        yaml_path = tmp_path / "test.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(minimal_profile_data, f)

        result = import_profile_from_file(session, yaml_path, update_existing=False)

        assert result.success is False
        assert "already exists" in (result.error or "")

    def test_import_validation_error(self, session, tmp_path):
        """Should report validation errors."""
        yaml_path = tmp_path / "invalid.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump({"name": "Missing fields"}, f)

        result = import_profile_from_file(session, yaml_path)

        assert result.success is False
        assert "Validation error" in (result.error or "")

    def test_import_from_directory(self, session, tmp_path, minimal_profile_data):
        """Should import profiles from directory."""
        for i in range(3):
            data = minimal_profile_data.copy()
            data["profile_id"] = f"test.profile.{i}"
            with open(tmp_path / f"profile{i}.yaml", "w") as f:
                yaml.dump(data, f)

        result = import_profiles_from_directory(session, tmp_path)

        assert result.total == 3
        assert result.succeeded == 3
        assert result.failed == 0

    def test_export_to_yaml(self, session, tmp_path, minimal_profile_data):
        """Should export profile to YAML file."""
        schema = ProfileSchema.model_validate(minimal_profile_data)
        create_profile(session, schema)
        session.commit()

        yaml_path = tmp_path / "exported.yaml"
        export_profile_to_file(session, "test.service.profile", yaml_path)

        assert yaml_path.exists()

        with open(yaml_path) as f:
            data = yaml.safe_load(f)
        assert data["profile_id"] == "test.service.profile"

    def test_export_to_json(self, session, tmp_path, minimal_profile_data):
        """Should export profile to JSON file."""
        schema = ProfileSchema.model_validate(minimal_profile_data)
        create_profile(session, schema)
        session.commit()

        json_path = tmp_path / "exported.json"
        export_profile_to_file(session, "test.service.profile", json_path)

        assert json_path.exists()

        with open(json_path) as f:
            data = json.load(f)
        assert data["profile_id"] == "test.service.profile"

    def test_export_not_found(self, session, tmp_path):
        """Should raise error when exporting nonexistent profile."""
        yaml_path = tmp_path / "exported.yaml"

        with pytest.raises(ProfileNotFoundError):
            export_profile_to_file(session, "nonexistent", yaml_path)

    def test_export_to_directory(self, session, tmp_path, minimal_profile_data):
        """Should export profiles to directory."""
        # Create multiple profiles
        for i in range(3):
            data = minimal_profile_data.copy()
            data["profile_id"] = f"test.export.{i}"
            data["name"] = f"Export Test {i}"
            schema = ProfileSchema.model_validate(data)
            create_profile(session, schema)
        session.commit()

        output_dir = tmp_path / "exports"
        count = export_profiles_to_directory(session, output_dir)

        assert count == 3
        assert len(list(output_dir.glob("*.yaml"))) == 3

    def test_export_to_directory_json(self, session, tmp_path, minimal_profile_data):
        """Should export profiles to directory as JSON."""
        schema = ProfileSchema.model_validate(minimal_profile_data)
        create_profile(session, schema)
        session.commit()

        output_dir = tmp_path / "exports"
        count = export_profiles_to_directory(session, output_dir, format="json")

        assert count == 1
        assert len(list(output_dir.glob("*.json"))) == 1

    def test_export_to_directory_specific_profiles(
        self, session, tmp_path, minimal_profile_data
    ):
        """Should export only specified profiles."""
        for i in range(3):
            data = minimal_profile_data.copy()
            data["profile_id"] = f"test.export.{i}"
            schema = ProfileSchema.model_validate(data)
            create_profile(session, schema)
        session.commit()

        output_dir = tmp_path / "exports"
        count = export_profiles_to_directory(
            session, output_dir, profile_ids=["test.export.0", "test.export.2"]
        )

        assert count == 2


class TestValidateProfileData:
    """Test standalone profile data validation."""

    def test_validate_valid_data(self, minimal_profile_data):
        """Should validate correct data."""
        schema = validate_profile_data(minimal_profile_data)
        assert schema.profile_id == "test.service.profile"

    def test_validate_invalid_data(self):
        """Should raise error for invalid data."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            validate_profile_data({"name": "Missing fields"})

    def test_validate_snapshot_without_policy(self):
        """Should raise error for snapshot without allow_snapshot."""
        data = {
            "profile_id": "test.snapshot",
            "name": "Snapshot Test",
            "device_id": "test",
            "openwrt_release": "snapshot",
            "target": "ath79",
            "subtarget": "generic",
            "imagebuilder_profile": "test",
        }

        with pytest.raises(ValueError) as exc_info:
            validate_profile_data(data)
        assert "allow_snapshot" in str(exc_info.value)
