"""Tests for FastAPI web GUI.

Uses TestClient to test /ui endpoints.
Reuses fixtures and patterns from test_web_api.py.
"""

import uuid

import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from openwrt_imagegen import __version__
from openwrt_imagegen.db import Base
from web.routers import builders, builds, config, flash, gui, health, profiles


def create_test_app() -> FastAPI:
    """Create a minimal FastAPI app for testing without lifespan."""
    application = FastAPI(
        title="OpenWrt Image Generator API",
        description="HTTP API for managing OpenWrt Image Builder profiles, "
        "builds, and TF/SD card flashing",
        version=__version__,
    )

    # Mount static files
    application.mount("/static", StaticFiles(directory="web/static"), name="static")

    # Include routers
    application.include_router(health.router, tags=["health"])
    application.include_router(config.router, prefix="/config", tags=["config"])
    application.include_router(profiles.router, prefix="/profiles", tags=["profiles"])
    application.include_router(builders.router, prefix="/builders", tags=["builders"])
    application.include_router(builds.router, prefix="/builds", tags=["builds"])
    application.include_router(flash.router, prefix="/flash", tags=["flash"])
    application.include_router(gui.router, prefix="/ui", tags=["gui"])

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
def client_with_profile(client):
    """Create a client with a pre-populated profile."""
    profile_data = {
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
    response = client.post("/profiles", json=profile_data)
    assert response.status_code == 201
    return client


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


class TestDashboard:
    """Tests for dashboard endpoint."""

    def test_dashboard_loads(self, client):
        """Test dashboard page loads successfully."""
        response = client.get("/ui/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Dashboard" in response.text
        assert "OpenWrt Image Generator" in response.text

    def test_dashboard_shows_counts(self, client):
        """Test dashboard shows profile/build/flash counts."""
        response = client.get("/ui/")
        assert response.status_code == 200
        # Should show counts (starting at 0)
        assert "0 profile" in response.text
        assert "0 build" in response.text
        assert "0 flash record" in response.text

    def test_dashboard_has_links(self, client):
        """Test dashboard has navigation links."""
        response = client.get("/ui/")
        assert response.status_code == 200
        assert "/ui/profiles" in response.text
        assert "/ui/builds" in response.text
        assert "/ui/flash" in response.text

    def test_dashboard_shows_config(self, client):
        """Test dashboard shows configuration details."""
        response = client.get("/ui/")
        assert response.status_code == 200
        assert (
            "verification_mode" in response.text.lower()
            or "Verification Mode" in response.text
        )


class TestProfilesList:
    """Tests for profiles list page."""

    def test_profiles_list_empty(self, client):
        """Test profiles list with no profiles."""
        response = client.get("/ui/profiles")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Profiles" in response.text
        assert "No profiles found" in response.text

    def test_profiles_list_with_data(self, client_with_profile):
        """Test profiles list shows profiles."""
        response = client_with_profile.get("/ui/profiles")
        assert response.status_code == 200
        assert "test.router.2305" in response.text
        assert "Test Router" in response.text
        assert "ath79" in response.text

    def test_profiles_list_filter_by_target(self, client_with_profile):
        """Test filtering profiles by target."""
        response = client_with_profile.get("/ui/profiles?target=ath79")
        assert response.status_code == 200
        assert "test.router.2305" in response.text

        # Filter with non-matching target
        response = client_with_profile.get("/ui/profiles?target=ramips")
        assert response.status_code == 200
        assert "No profiles found" in response.text

    def test_profiles_list_filter_by_release(self, client_with_profile):
        """Test filtering profiles by release."""
        response = client_with_profile.get("/ui/profiles?release=23.05.2")
        assert response.status_code == 200
        assert "test.router.2305" in response.text


class TestProfileDetail:
    """Tests for profile detail page."""

    def test_profile_detail(self, client_with_profile):
        """Test profile detail page loads."""
        response = client_with_profile.get("/ui/profiles/test.router.2305")
        assert response.status_code == 200
        assert "test.router.2305" in response.text
        assert "Test Router" in response.text
        assert "tplink_archer-c7-v2" in response.text
        assert "luci" in response.text

    def test_profile_detail_not_found(self, client):
        """Test profile detail 404 for non-existent profile."""
        response = client.get("/ui/profiles/non-existent")
        assert response.status_code == 404

    def test_profile_detail_has_build_form(self, client_with_profile):
        """Test profile detail has build form."""
        response = client_with_profile.get("/ui/profiles/test.router.2305")
        assert response.status_code == 200
        assert "Build this profile" in response.text or "Build Image" in response.text
        assert "/ui/builds" in response.text and "action=" in response.text


class TestBuildsList:
    """Tests for builds list page."""

    def test_builds_list_empty(self, client):
        """Test builds list with no builds."""
        response = client.get("/ui/builds")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Builds" in response.text
        assert "No builds found" in response.text

    def test_builds_list_filter_by_status(self, client):
        """Test filtering builds by status."""
        response = client.get("/ui/builds?status=succeeded")
        assert response.status_code == 200
        # Invalid status is ignored
        response = client.get("/ui/builds?status=invalid")
        assert response.status_code == 200


class TestBuildDetail:
    """Tests for build detail page."""

    def test_build_detail_not_found(self, client):
        """Test build detail 404 for non-existent build."""
        response = client.get("/ui/builds/999")
        assert response.status_code == 404


class TestBuildCreate:
    """Tests for build creation endpoint."""

    def test_build_create_profile_not_found(self, client):
        """Test build create returns 404 for non-existent profile."""
        response = client.post(
            "/ui/builds",
            data={"profile_id": "non-existent", "force_rebuild": "false"},
        )
        assert response.status_code == 404

    def test_build_create_redirects(self, client_with_profile):
        """Test build create redirects (303) on success."""
        response = client_with_profile.post(
            "/ui/builds",
            data={"profile_id": "test.router.2305", "force_rebuild": "false"},
            follow_redirects=False,
        )
        # Should redirect (303) to profile page (since no builds exist yet)
        assert response.status_code == 303
        assert "/ui/profiles/test.router.2305" in response.headers.get("location", "")


class TestFlashList:
    """Tests for flash records list page."""

    def test_flash_list_empty(self, client):
        """Test flash list with no records."""
        response = client.get("/ui/flash")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Flash Records" in response.text
        assert "No flash records found" in response.text

    def test_flash_list_filter_by_status(self, client):
        """Test filtering flash records by status."""
        response = client.get("/ui/flash?status=succeeded")
        assert response.status_code == 200


class TestFlashWizard:
    """Tests for flash wizard page."""

    def test_flash_wizard_loads(self, client):
        """Test flash wizard page loads."""
        response = client.get("/ui/flash/new")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Flash Wizard" in response.text
        assert "Warning" in response.text
        assert "device_path" in response.text

    def test_flash_wizard_with_artifact_not_found(self, client):
        """Test flash wizard handles non-existent artifact."""
        response = client.get("/ui/flash/new?artifact_id=999")
        assert response.status_code == 200
        assert "Artifact not found" in response.text

    def test_flash_wizard_confirmation_required(self, client):
        """Test flash wizard requires device confirmation."""
        response = client.post(
            "/ui/flash",
            data={
                "artifact_id": "1",
                "device_path": "/dev/sdb",
                "confirmation": "/dev/sdc",  # Wrong confirmation
                "dry_run": "true",
            },
        )
        assert response.status_code == 400
        assert "confirmation does not match" in response.text.lower()

    def test_flash_wizard_force_required_for_real_write(self, client):
        """Test flash wizard requires force flag for real writes."""
        response = client.post(
            "/ui/flash",
            data={
                "artifact_id": "1",
                "device_path": "/dev/sdb",
                "confirmation": "/dev/sdb",
                "dry_run": "false",  # Real write
                "force": "false",  # No force
            },
        )
        assert response.status_code == 400
        assert "force" in response.text.lower()

    def test_flash_wizard_artifact_not_found(self, client):
        """Test flash wizard returns 404 for non-existent artifact."""
        response = client.post(
            "/ui/flash",
            data={
                "artifact_id": "999",
                "device_path": "/dev/sdb",
                "confirmation": "/dev/sdb",
                "dry_run": "true",
                "force": "true",
            },
        )
        assert response.status_code == 404


class TestFlashDetail:
    """Tests for flash record detail page."""

    def test_flash_detail_not_found(self, client):
        """Test flash detail 404 for non-existent record."""
        response = client.get("/ui/flash/999")
        assert response.status_code == 404


class TestNavigation:
    """Tests for navigation between pages."""

    def test_navigation_links_work(self, client):
        """Test that navigation links are present and correct."""
        response = client.get("/ui/")
        assert response.status_code == 200
        # Check navigation menu links (URLs include testserver prefix)
        assert "/ui/" in response.text
        assert "/ui/profiles" in response.text
        assert "/ui/builds" in response.text
        assert "/ui/flash" in response.text

    def test_back_to_list_links(self, client_with_profile):
        """Test back-to-list links on detail pages."""
        # Profile detail should have back link
        response = client_with_profile.get("/ui/profiles/test.router.2305")
        assert response.status_code == 200
        assert "Back to List" in response.text or "/ui/profiles" in response.text


class TestStaticFiles:
    """Tests for static file serving."""

    def test_css_file_served(self, client):
        """Test CSS file is served correctly."""
        response = client.get("/static/css/style.css")
        assert response.status_code == 200
        assert "text/css" in response.headers["content-type"]

    def test_js_file_served(self, client):
        """Test JavaScript file is served correctly."""
        response = client.get("/static/js/app.js")
        assert response.status_code == 200
        assert "javascript" in response.headers["content-type"]
