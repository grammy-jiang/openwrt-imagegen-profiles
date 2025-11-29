"""Tests for FastAPI web API.

Uses TestClient to test all endpoints.
"""

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from openwrt_imagegen import __version__
from openwrt_imagegen.db import Base
from web.routers import builders, builds, config, flash, health, profiles


def create_test_app() -> FastAPI:
    """Create a minimal FastAPI app for testing without lifespan."""
    application = FastAPI(
        title="OpenWrt Image Generator API",
        description="HTTP API for managing OpenWrt Image Builder profiles, "
        "builds, and TF/SD card flashing",
        version=__version__,
    )

    # Include routers
    application.include_router(health.router, tags=["health"])
    application.include_router(config.router, prefix="/config", tags=["config"])
    application.include_router(profiles.router, prefix="/profiles", tags=["profiles"])
    application.include_router(builders.router, prefix="/builders", tags=["builders"])
    application.include_router(builds.router, prefix="/builds", tags=["builds"])
    application.include_router(flash.router, prefix="/flash", tags=["flash"])

    return application


@pytest.fixture
def client(tmp_path):
    """Create a test client with a fresh SQLite database in tmp_path.

    Each test gets a fresh database file.
    """
    # Create unique database file for this test
    db_file = tmp_path / f"test_{uuid.uuid4().hex[:8]}.db"
    engine = create_engine(f"sqlite:///{db_file}", echo=False)

    # Create all tables
    Base.metadata.create_all(engine)

    # Create test app without lifespan to avoid DB conflicts
    app = create_test_app()
    # Set session factory
    app.state.session_factory = sessionmaker(bind=engine)

    with TestClient(app) as test_client:
        yield test_client

    # Clean up
    engine.dispose()
    if db_file.exists():
        db_file.unlink()


@pytest.fixture
def sample_profile_data():
    """Sample profile data for testing."""
    return {
        "profile_id": "test.router.2305",
        "name": "Test Router",
        "device_id": "test-router",
        "openwrt_release": "23.05.2",
        "target": "ath79",
        "subtarget": "generic",
        "imagebuilder_profile": "tplink_archer-c7-v2",
        "tags": ["test", "router"],
        "packages": ["luci", "luci-ssl"],
    }


class TestHealthEndpoints:
    """Tests for health and root endpoints."""

    def test_health(self, client):
        """Test health endpoint returns OK status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["version"] == __version__

    def test_root(self, client):
        """Test root endpoint returns API name and version."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "OpenWrt Image Generator API"
        assert data["version"] == __version__


class TestConfigEndpoints:
    """Tests for configuration endpoints."""

    def test_get_config(self, client):
        """Test getting configuration."""
        response = client.get("/config")
        assert response.status_code == 200
        data = response.json()
        assert "cache_dir" in data
        assert "artifacts_dir" in data
        assert "offline" in data
        assert "log_level" in data


class TestProfileEndpoints:
    """Tests for profile management endpoints."""

    def test_list_profiles_empty(self, client):
        """Test listing profiles when empty."""
        response = client.get("/profiles")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_profile(self, client, sample_profile_data):
        """Test creating a profile."""
        response = client.post("/profiles", json=sample_profile_data)
        assert response.status_code == 201
        data = response.json()
        assert data["profile_id"] == sample_profile_data["profile_id"]
        assert data["name"] == sample_profile_data["name"]
        assert data["device_id"] == sample_profile_data["device_id"]

    def test_create_profile_duplicate(self, client, sample_profile_data):
        """Test creating a duplicate profile returns 409."""
        client.post("/profiles", json=sample_profile_data)
        response = client.post("/profiles", json=sample_profile_data)
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "profile_exists"

    def test_get_profile(self, client, sample_profile_data):
        """Test getting a profile by ID."""
        client.post("/profiles", json=sample_profile_data)
        response = client.get(f"/profiles/{sample_profile_data['profile_id']}")
        assert response.status_code == 200
        data = response.json()
        assert data["profile_id"] == sample_profile_data["profile_id"]

    def test_get_profile_not_found(self, client):
        """Test getting a non-existent profile returns 404."""
        response = client.get("/profiles/non-existent")
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "profile_not_found"

    def test_get_profile_with_meta(self, client, sample_profile_data):
        """Test getting a profile with metadata."""
        client.post("/profiles", json=sample_profile_data)
        response = client.get(
            f"/profiles/{sample_profile_data['profile_id']}?include_meta=true"
        )
        assert response.status_code == 200
        data = response.json()
        assert "meta" in data

    def test_update_profile(self, client, sample_profile_data):
        """Test updating a profile."""
        client.post("/profiles", json=sample_profile_data)
        updated_data = sample_profile_data.copy()
        updated_data["name"] = "Updated Router Name"
        response = client.put(
            f"/profiles/{sample_profile_data['profile_id']}", json=updated_data
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Router Name"

    def test_update_profile_not_found(self, client, sample_profile_data):
        """Test updating a non-existent profile returns 404."""
        response = client.put("/profiles/non-existent", json=sample_profile_data)
        assert response.status_code == 400  # profile_id mismatch first

    def test_update_profile_id_mismatch(self, client, sample_profile_data):
        """Test updating with mismatched profile_id returns 400."""
        client.post("/profiles", json=sample_profile_data)
        updated_data = sample_profile_data.copy()
        updated_data["profile_id"] = "different-id"
        response = client.put(
            f"/profiles/{sample_profile_data['profile_id']}", json=updated_data
        )
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "profile_id_mismatch"

    def test_delete_profile(self, client, sample_profile_data):
        """Test deleting a profile."""
        client.post("/profiles", json=sample_profile_data)
        response = client.delete(f"/profiles/{sample_profile_data['profile_id']}")
        assert response.status_code == 204

        # Verify it's deleted
        response = client.get(f"/profiles/{sample_profile_data['profile_id']}")
        assert response.status_code == 404

    def test_delete_profile_not_found(self, client):
        """Test deleting a non-existent profile returns 404."""
        response = client.delete("/profiles/non-existent")
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "profile_not_found"

    def test_list_profiles_with_filter(self, client, sample_profile_data):
        """Test listing profiles with filters."""
        client.post("/profiles", json=sample_profile_data)
        response = client.get("/profiles?target=ath79")
        assert response.status_code == 200
        profiles = response.json()
        assert len(profiles) == 1
        assert profiles[0]["target"] == "ath79"

    def test_list_profiles_filter_no_match(self, client, sample_profile_data):
        """Test listing profiles with filter that matches nothing."""
        client.post("/profiles", json=sample_profile_data)
        response = client.get("/profiles?target=ramips")
        assert response.status_code == 200
        assert response.json() == []


class TestBuildersEndpoints:
    """Tests for Image Builder endpoints."""

    def test_list_builders_empty(self, client):
        """Test listing builders when empty."""
        response = client.get("/builders")
        assert response.status_code == 200
        assert response.json() == []

    def test_get_cache_info(self, client):
        """Test getting cache info."""
        response = client.get("/builders/info")
        assert response.status_code == 200
        data = response.json()
        assert "cache_dir" in data
        assert "total_size_bytes" in data

    def test_get_builder_not_found(self, client):
        """Test getting a non-existent builder returns 404."""
        response = client.get("/builders/23.05.2/ath79/generic")
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "imagebuilder_not_found"

    def test_list_builders_invalid_state(self, client):
        """Test listing builders with invalid state returns 400."""
        response = client.get("/builders?state=invalid")
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "invalid_state"


class TestBuildsEndpoints:
    """Tests for build management endpoints."""

    def test_list_builds_empty(self, client):
        """Test listing builds when empty."""
        response = client.get("/builds")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_builds_invalid_status(self, client):
        """Test listing builds with invalid status returns 400."""
        response = client.get("/builds?status=invalid")
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "invalid_status"

    def test_get_build_not_found(self, client):
        """Test getting a non-existent build returns 404."""
        response = client.get("/builds/999")
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "build_not_found"

    def test_get_build_artifacts_not_found(self, client):
        """Test getting artifacts for non-existent build returns 404."""
        response = client.get("/builds/999/artifacts")
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "build_not_found"

    def test_batch_build_no_filter(self, client):
        """Test batch build without filter returns 400."""
        response = client.post("/builds/batch", json={})
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "no_filter"

    def test_batch_build_invalid_mode(self, client):
        """Test batch build with invalid mode returns 400."""
        response = client.post(
            "/builds/batch", json={"profile_ids": ["test"], "mode": "invalid"}
        )
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "invalid_mode"


class TestFlashEndpoints:
    """Tests for flash operation endpoints."""

    def test_list_flash_records_empty(self, client):
        """Test listing flash records when empty."""
        response = client.get("/flash")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_flash_records_invalid_status(self, client):
        """Test listing flash records with invalid status returns 400."""
        response = client.get("/flash?status=invalid")
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "invalid_status"

    def test_flash_artifact_not_found(self, client):
        """Test flashing non-existent artifact returns 404."""
        response = client.post(
            "/flash",
            json={"artifact_id": 999, "device_path": "/dev/sdb"},
        )
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "artifact_not_found"
