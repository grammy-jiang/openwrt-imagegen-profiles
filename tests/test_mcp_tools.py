"""Tests for MCP tools with idempotency and error code verification.

These tests verify:
- MCP tools return correct structured responses
- Error codes are stable and match OPERATIONS.md taxonomy
- Build operations are idempotent (cache-aware)
- Safety requirements for flash are enforced
"""

import contextlib
import os
import tempfile
from unittest.mock import patch

import pytest

from openwrt_imagegen.db import create_all_tables, get_engine, get_session_factory


@pytest.fixture(autouse=True)
def isolated_db():
    """Create an isolated temp database for each test.

    This fixture automatically sets up a fresh temp database for
    each test and patches the db module to use it.
    """
    import openwrt_imagegen.db as db_module

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_url = f"sqlite:///{path}"

    # Patch environment
    with patch.dict(os.environ, {"OWRT_IMG_DB_URL": db_url}):
        # Reset db module state
        db_module._engine = None
        db_module._session_factory = None

        # Initialize db
        engine = get_engine()
        create_all_tables(engine)

        yield db_url

    # Cleanup
    db_module._engine = None
    db_module._session_factory = None
    with contextlib.suppress(FileNotFoundError):
        os.unlink(path)


@pytest.fixture
def sample_profile_data():
    """Sample profile data for testing."""
    return {
        "profile_id": "test.device.profile",
        "name": "Test Device Profile",
        "device_id": "test-device",
        "openwrt_release": "23.05.3",
        "target": "ramips",
        "subtarget": "mt7621",
        "imagebuilder_profile": "device_test",
        "packages": ["luci", "luci-ssl"],
        "tags": ["test", "lab"],
    }


@pytest.fixture
def session_with_profile(sample_profile_data):
    """Create a session with a sample profile already created."""
    from openwrt_imagegen.profiles.schema import ProfileSchema
    from openwrt_imagegen.profiles.service import create_profile

    factory = get_session_factory(get_engine())
    with factory() as session:
        schema = ProfileSchema(**sample_profile_data)
        create_profile(session, schema)
        session.commit()
        yield session


class TestListProfiles:
    """Tests for list_profiles MCP tool."""

    def test_list_profiles_empty(self):
        """Test listing profiles when database is empty."""
        from mcp_server.server import list_profiles

        result = list_profiles()

        assert result.success is True
        assert result.profiles == []
        assert result.total == 0
        assert result.error is None

    def test_list_profiles_with_data(self, session_with_profile, sample_profile_data):
        """Test listing profiles with data in database."""
        from mcp_server.server import list_profiles

        result = list_profiles()

        assert result.success is True
        assert result.total == 1
        assert len(result.profiles) == 1
        assert result.profiles[0].profile_id == sample_profile_data["profile_id"]

    def test_list_profiles_with_filter(self, session_with_profile, sample_profile_data):
        """Test filtering profiles by release."""
        from mcp_server.server import list_profiles

        # Filter by matching release
        result = list_profiles(release="23.05.3")
        assert result.success is True
        assert result.total == 1

        # Filter by non-matching release
        result = list_profiles(release="24.01.0")
        assert result.success is True
        assert result.total == 0


class TestGetProfile:
    """Tests for get_profile MCP tool."""

    def test_get_profile_not_found(self):
        """Test getting a profile that doesn't exist."""
        from mcp_server.errors import PROFILE_NOT_FOUND
        from mcp_server.server import get_profile

        result = get_profile(profile_id="nonexistent.profile")

        assert result.success is False
        assert result.profile is None
        assert result.error is not None
        assert result.error["code"] == PROFILE_NOT_FOUND

    def test_get_profile_success(self, session_with_profile, sample_profile_data):
        """Test getting a profile that exists."""
        from mcp_server.server import get_profile

        result = get_profile(profile_id=sample_profile_data["profile_id"])

        assert result.success is True
        assert result.profile is not None
        assert result.profile.profile_id == sample_profile_data["profile_id"]
        assert result.profile.name == sample_profile_data["name"]
        assert result.error is None


class TestBuildImage:
    """Tests for build_image MCP tool - idempotency and error codes."""

    def test_build_image_profile_not_found(self):
        """Test building with nonexistent profile returns correct error code."""
        from mcp_server.errors import PROFILE_NOT_FOUND
        from mcp_server.server import build_image

        result = build_image(profile_id="nonexistent.profile")

        assert result.success is False
        assert result.error is not None
        assert result.error["code"] == PROFILE_NOT_FOUND

    def test_build_image_returns_cache_hit_flag(
        self, session_with_profile, sample_profile_data
    ):
        """Test that build_image returns cache_hit flag.

        Note: Full idempotency testing requires mocking the Image Builder,
        so this test just verifies the response structure.
        """
        from mcp_server.server import build_image

        # Attempt build (will fail due to no Image Builder, but structure is correct)
        result = build_image(profile_id=sample_profile_data["profile_id"])

        # Response should have proper structure
        assert hasattr(result, "cache_hit")
        assert hasattr(result, "build_id")
        assert hasattr(result, "status")
        assert hasattr(result, "artifacts")
        assert hasattr(result, "log_path")


class TestBuildImagesBatch:
    """Tests for build_images_batch MCP tool."""

    def test_batch_build_requires_filter(self):
        """Test that batch build requires at least one filter."""
        from mcp_server.errors import VALIDATION_ERROR
        from mcp_server.server import build_images_batch

        result = build_images_batch()

        assert result.success is False
        assert result.error is not None
        assert result.error["code"] == VALIDATION_ERROR

    def test_batch_build_invalid_mode(self):
        """Test that batch build validates mode parameter."""
        from mcp_server.errors import VALIDATION_ERROR
        from mcp_server.server import build_images_batch

        result = build_images_batch(
            profile_ids=["test.profile"],
            mode="invalid-mode",
        )

        assert result.success is False
        assert result.error is not None
        assert result.error["code"] == VALIDATION_ERROR

    def test_batch_build_valid_modes(self, session_with_profile, sample_profile_data):
        """Test that batch build accepts valid modes."""
        from mcp_server.server import build_images_batch

        # Test best-effort mode
        result = build_images_batch(
            profile_ids=[sample_profile_data["profile_id"]],
            mode="best-effort",
        )
        assert result.mode == "best-effort"

        # Test fail-fast mode
        result = build_images_batch(
            profile_ids=[sample_profile_data["profile_id"]],
            mode="fail-fast",
        )
        assert result.mode == "fail-fast"

    def test_batch_build_returns_per_profile_results(self, sample_profile_data):
        """Test that batch build returns per-profile results."""
        from mcp_server.server import build_images_batch
        from openwrt_imagegen.profiles.schema import ProfileSchema
        from openwrt_imagegen.profiles.service import create_profile

        factory = get_session_factory(get_engine())
        with factory() as session:
            # Create profiles
            for i in range(2):
                data = sample_profile_data.copy()
                data["profile_id"] = f"test.profile.{i}"
                schema = ProfileSchema(**data)
                create_profile(session, schema)
            session.commit()

        result = build_images_batch(
            profile_ids=["test.profile.0", "test.profile.1"],
        )

        # Should have results for both profiles
        assert len(result.results) == 2
        assert result.total == 2
        # Each result should have profile_id
        profile_ids = {r.profile_id for r in result.results}
        assert "test.profile.0" in profile_ids
        assert "test.profile.1" in profile_ids


class TestListBuilds:
    """Tests for list_builds MCP tool."""

    def test_list_builds_empty(self):
        """Test listing builds when none exist."""
        from mcp_server.server import list_builds

        result = list_builds()

        assert result.success is True
        assert result.builds == []
        assert result.total == 0

    def test_list_builds_invalid_status(self):
        """Test listing builds with invalid status."""
        from mcp_server.errors import VALIDATION_ERROR
        from mcp_server.server import list_builds

        result = list_builds(status="invalid-status")

        assert result.success is False
        assert result.error is not None
        assert result.error["code"] == VALIDATION_ERROR

    def test_list_builds_profile_not_found(self):
        """Test listing builds for nonexistent profile."""
        from mcp_server.errors import PROFILE_NOT_FOUND
        from mcp_server.server import list_builds

        result = list_builds(profile_id="nonexistent.profile")

        assert result.success is False
        assert result.error is not None
        assert result.error["code"] == PROFILE_NOT_FOUND


class TestListArtifacts:
    """Tests for list_artifacts MCP tool."""

    def test_list_artifacts_empty(self):
        """Test listing artifacts when none exist."""
        from mcp_server.server import list_artifacts

        result = list_artifacts()

        assert result.success is True
        assert result.artifacts == []
        assert result.total == 0

    def test_list_artifacts_build_not_found(self):
        """Test listing artifacts for nonexistent build."""
        from mcp_server.errors import BUILD_NOT_FOUND
        from mcp_server.server import list_artifacts

        result = list_artifacts(build_id=99999)

        assert result.success is False
        assert result.error is not None
        assert result.error["code"] == BUILD_NOT_FOUND


class TestFlashArtifact:
    """Tests for flash_artifact MCP tool - safety requirements."""

    def test_flash_requires_force_for_actual_write(self):
        """Test that flash requires force=True for actual writes."""
        from mcp_server.errors import VALIDATION_ERROR
        from mcp_server.server import flash_artifact

        result = flash_artifact(
            artifact_id=1,
            device_path="/dev/sdz",
            dry_run=False,
            force=False,  # Missing force flag
        )

        assert result.success is False
        assert result.error is not None
        assert result.error["code"] == VALIDATION_ERROR

    def test_flash_dry_run_does_not_require_force(self):
        """Test that dry_run mode doesn't require force flag."""
        from mcp_server.errors import ARTIFACT_NOT_FOUND
        from mcp_server.server import flash_artifact

        # Will fail with artifact_not_found, but not validation error
        result = flash_artifact(
            artifact_id=99999,
            device_path="/dev/sdz",
            dry_run=True,
            force=False,
        )

        # Should fail with artifact not found, not validation error
        assert result.success is False
        assert result.error is not None
        assert result.error["code"] == ARTIFACT_NOT_FOUND

    def test_flash_artifact_not_found(self):
        """Test flash with nonexistent artifact."""
        from mcp_server.errors import ARTIFACT_NOT_FOUND
        from mcp_server.server import flash_artifact

        result = flash_artifact(
            artifact_id=99999,
            device_path="/dev/sdz",
            dry_run=True,
        )

        assert result.success is False
        assert result.error is not None
        assert result.error["code"] == ARTIFACT_NOT_FOUND


class TestErrorCodes:
    """Tests verifying error codes align with OPERATIONS.md taxonomy."""

    def test_profile_not_found_code(self):
        """Verify profile not found uses correct code."""
        from mcp_server.errors import PROFILE_NOT_FOUND, profile_not_found

        error = profile_not_found("test.profile")
        assert error.code == PROFILE_NOT_FOUND
        assert error.code == "profile_not_found"

    def test_build_not_found_code(self):
        """Verify build not found uses correct code."""
        from mcp_server.errors import BUILD_NOT_FOUND, build_not_found

        error = build_not_found(123)
        assert error.code == BUILD_NOT_FOUND
        assert error.code == "build_not_found"

    def test_artifact_not_found_code(self):
        """Verify artifact not found uses correct code."""
        from mcp_server.errors import ARTIFACT_NOT_FOUND, artifact_not_found

        error = artifact_not_found(456)
        assert error.code == ARTIFACT_NOT_FOUND
        assert error.code == "artifact_not_found"

    def test_validation_error_code(self):
        """Verify validation error uses correct code."""
        from mcp_server.errors import VALIDATION_ERROR, validation_error

        error = validation_error("Invalid input")
        assert error.code == VALIDATION_ERROR
        assert error.code == "validation"

    def test_error_to_dict(self):
        """Verify error serialization includes required fields."""
        from mcp_server.errors import make_error

        error = make_error(
            "test_code",
            "Test message",
            details={"key": "value"},
            log_path="/tmp/test.log",
        )

        result = error.to_dict()

        assert result["code"] == "test_code"
        assert result["message"] == "Test message"
        assert result["details"] == {"key": "value"}
        assert result["log_path"] == "/tmp/test.log"


class TestIdempotency:
    """Tests verifying idempotent behavior of MCP tools."""

    def test_list_profiles_idempotent(self, session_with_profile, sample_profile_data):
        """Test that list_profiles returns same results on repeated calls."""
        from mcp_server.server import list_profiles

        # Call multiple times
        result1 = list_profiles()
        result2 = list_profiles()
        result3 = list_profiles()

        # All calls should return same data
        assert result1.total == result2.total == result3.total == 1
        assert result1.profiles[0].profile_id == result2.profiles[0].profile_id
        assert result2.profiles[0].profile_id == result3.profiles[0].profile_id

    def test_get_profile_idempotent(self, session_with_profile, sample_profile_data):
        """Test that get_profile returns same results on repeated calls."""
        from mcp_server.server import get_profile

        pid = sample_profile_data["profile_id"]

        # Call multiple times
        result1 = get_profile(profile_id=pid)
        result2 = get_profile(profile_id=pid)
        result3 = get_profile(profile_id=pid)

        # All calls should return same data
        assert result1.profile is not None
        assert result2.profile is not None
        assert result3.profile is not None
        assert result1.profile.profile_id == result2.profile.profile_id
        assert result2.profile.profile_id == result3.profile.profile_id
        assert result1.profile.name == result2.profile.name
