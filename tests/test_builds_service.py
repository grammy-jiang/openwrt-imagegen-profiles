"""Tests for builds/service.py module.

Tests build service operations with mocked dependencies.
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from openwrt_imagegen.builds.models import Artifact, BuildRecord
from openwrt_imagegen.builds.service import (
    BuildNotFoundError,
    build_lock,
    get_build,
    get_build_artifacts,
    get_build_or_none,
    list_builds,
)
from openwrt_imagegen.db import Base
from openwrt_imagegen.flash.models import (
    FlashRecord,  # noqa: F401 - needed for ORM relationships
)
from openwrt_imagegen.imagebuilder.models import ImageBuilder
from openwrt_imagegen.profiles.models import Profile
from openwrt_imagegen.types import BuildStatus, ImageBuilderState


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
def profile(session):
    """Create a test profile."""
    p = Profile(
        profile_id="test.service",
        name="Service Test",
        device_id="service-device",
        openwrt_release="23.05.3",
        target="ath79",
        subtarget="generic",
        imagebuilder_profile="service-profile",
    )
    session.add(p)
    session.commit()
    return p


@pytest.fixture
def imagebuilder(session, tmp_path):
    """Create a test imagebuilder."""
    root_dir = tmp_path / "imagebuilder"
    root_dir.mkdir()
    (root_dir / "Makefile").touch()
    (root_dir / "target").mkdir()
    (root_dir / "packages").mkdir()

    ib = ImageBuilder(
        openwrt_release="23.05.3",
        target="ath79",
        subtarget="generic",
        upstream_url="https://example.com/ib.tar.xz",
        root_dir=str(root_dir),
        state=ImageBuilderState.READY.value,
    )
    session.add(ib)
    session.commit()
    return ib


@pytest.fixture
def build_record(session, profile, imagebuilder):
    """Create a test build record."""
    build = BuildRecord(
        profile_id=profile.id,
        imagebuilder_id=imagebuilder.id,
        cache_key="sha256:test123",
        status=BuildStatus.SUCCEEDED.value,
    )
    session.add(build)
    session.commit()
    return build


class TestBuildLock:
    """Tests for build_lock context manager."""

    def test_acquires_and_releases_lock(self, tmp_path):
        """Should acquire and release lock."""
        lock_dir = tmp_path / "locks"

        with build_lock(lock_dir, "sha256:testkey"):
            # Lock acquired
            lock_file = lock_dir / "build_sha256_testkey.lock"
            assert lock_file.exists()

        # Lock released (file still exists but unlocked)
        assert lock_file.exists()

    def test_creates_lock_directory(self, tmp_path):
        """Should create lock directory if needed."""
        lock_dir = tmp_path / "deep" / "nested" / "locks"

        with build_lock(lock_dir, "sha256:testkey"):
            assert lock_dir.exists()

    def test_reentrant_with_different_keys(self, tmp_path):
        """Should allow locks on different keys."""
        lock_dir = tmp_path / "locks"

        with (
            build_lock(lock_dir, "sha256:key1"),
            build_lock(lock_dir, "sha256:key2"),
        ):
            # Both locks acquired
            assert (lock_dir / "build_sha256_key1.lock").exists()
            assert (lock_dir / "build_sha256_key2.lock").exists()


class TestGetBuild:
    """Tests for get_build function."""

    def test_returns_build(self, session, build_record):
        """Should return build by ID."""
        result = get_build(session, build_record.id)
        assert result.id == build_record.id
        assert result.cache_key == "sha256:test123"

    def test_raises_not_found(self, session):
        """Should raise BuildNotFoundError for invalid ID."""
        with pytest.raises(BuildNotFoundError) as exc_info:
            get_build(session, 99999)

        assert exc_info.value.build_id == 99999


class TestGetBuildOrNone:
    """Tests for get_build_or_none function."""

    def test_returns_build(self, session, build_record):
        """Should return build by ID."""
        result = get_build_or_none(session, build_record.id)
        assert result is not None
        assert result.id == build_record.id

    def test_returns_none_not_found(self, session):
        """Should return None for invalid ID."""
        result = get_build_or_none(session, 99999)
        assert result is None


class TestListBuilds:
    """Tests for list_builds function."""

    def test_returns_all_builds(self, session, profile, imagebuilder):
        """Should return all builds."""
        # Create multiple builds
        for i in range(3):
            build = BuildRecord(
                profile_id=profile.id,
                imagebuilder_id=imagebuilder.id,
                cache_key=f"sha256:key{i}",
                status=BuildStatus.SUCCEEDED.value,
            )
            session.add(build)
        session.commit()

        result = list_builds(session)
        assert len(result) == 3

    def test_filter_by_profile(self, session, profile, imagebuilder):
        """Should filter by profile_id."""
        # Create another profile and build
        profile2 = Profile(
            profile_id="test.other",
            name="Other",
            device_id="other-device",
            openwrt_release="23.05.3",
            target="ath79",
            subtarget="generic",
            imagebuilder_profile="other-profile",
        )
        session.add(profile2)
        session.commit()

        build1 = BuildRecord(
            profile_id=profile.id,
            imagebuilder_id=imagebuilder.id,
            cache_key="sha256:build1",
        )
        build2 = BuildRecord(
            profile_id=profile2.id,
            imagebuilder_id=imagebuilder.id,
            cache_key="sha256:build2",
        )
        session.add_all([build1, build2])
        session.commit()

        result = list_builds(session, profile_id=profile.id)
        assert len(result) == 1
        assert result[0].cache_key == "sha256:build1"

    def test_filter_by_status(self, session, profile, imagebuilder):
        """Should filter by status."""
        build1 = BuildRecord(
            profile_id=profile.id,
            imagebuilder_id=imagebuilder.id,
            cache_key="sha256:succeeded",
            status=BuildStatus.SUCCEEDED.value,
        )
        build2 = BuildRecord(
            profile_id=profile.id,
            imagebuilder_id=imagebuilder.id,
            cache_key="sha256:failed",
            status=BuildStatus.FAILED.value,
        )
        session.add_all([build1, build2])
        session.commit()

        result = list_builds(session, status=BuildStatus.SUCCEEDED)
        assert len(result) == 1
        assert result[0].cache_key == "sha256:succeeded"

    def test_respects_limit(self, session, profile, imagebuilder):
        """Should respect limit parameter."""
        for i in range(10):
            build = BuildRecord(
                profile_id=profile.id,
                imagebuilder_id=imagebuilder.id,
                cache_key=f"sha256:key{i}",
            )
            session.add(build)
        session.commit()

        result = list_builds(session, limit=5)
        assert len(result) == 5


class TestGetBuildArtifacts:
    """Tests for get_build_artifacts function."""

    def test_returns_artifacts(self, session, build_record):
        """Should return artifacts for build."""
        artifact1 = Artifact(
            build_id=build_record.id,
            kind="sysupgrade",
            relative_path="a.bin",
            filename="a.bin",
            size_bytes=1000,
            sha256="a" * 64,
        )
        artifact2 = Artifact(
            build_id=build_record.id,
            kind="factory",
            relative_path="b.bin",
            filename="b.bin",
            size_bytes=2000,
            sha256="b" * 64,
        )
        session.add_all([artifact1, artifact2])
        session.commit()

        result = get_build_artifacts(session, build_record.id)
        assert len(result) == 2

    def test_raises_not_found(self, session):
        """Should raise BuildNotFoundError for invalid build."""
        with pytest.raises(BuildNotFoundError):
            get_build_artifacts(session, 99999)

    def test_empty_artifacts(self, session, build_record):
        """Should return empty list for build without artifacts."""
        result = get_build_artifacts(session, build_record.id)
        assert result == []


class TestBuildOrReuseMocked:
    """Tests for build_or_reuse with mocked runner."""

    @pytest.fixture
    def mock_settings(self, tmp_path):
        """Create mock settings."""
        settings = MagicMock()
        settings.cache_dir = tmp_path / "cache"
        settings.cache_dir.mkdir()
        settings.artifacts_dir = tmp_path / "artifacts"
        settings.artifacts_dir.mkdir()
        settings.build_timeout = 3600
        return settings

    def test_cache_hit_returns_existing(
        self, session, profile, imagebuilder, mock_settings
    ):
        """Should return existing build on cache hit."""
        from openwrt_imagegen.builds.service import build_or_reuse
        from openwrt_imagegen.profiles.service import profile_to_schema

        # Create existing successful build
        existing_build = BuildRecord(
            profile_id=profile.id,
            imagebuilder_id=imagebuilder.id,
            cache_key="sha256:testkey",
            status=BuildStatus.SUCCEEDED.value,
            input_snapshot={"test": "data"},
        )
        session.add(existing_build)
        session.commit()

        profile_schema = profile_to_schema(profile)

        # Mock cache key computation to return matching key
        with patch(
            "openwrt_imagegen.builds.service.compute_cache_key_from_profile"
        ) as mock_cache_key:
            mock_inputs = MagicMock()
            mock_inputs.to_dict.return_value = {"test": "data"}
            mock_cache_key.return_value = ("sha256:testkey", mock_inputs)

            with patch(
                "openwrt_imagegen.builds.service.has_overlay_content"
            ) as mock_overlay:
                mock_overlay.return_value = False

                result, is_cache_hit = build_or_reuse(
                    session=session,
                    profile=profile,
                    profile_schema=profile_schema,
                    imagebuilder=imagebuilder,
                    settings=mock_settings,
                )

                assert is_cache_hit is True
                assert result.id == existing_build.id

    def test_force_rebuild_ignores_cache(
        self, session, profile, imagebuilder, mock_settings, tmp_path
    ):
        """Should ignore cache when force_rebuild=True."""
        from openwrt_imagegen.builds.service import build_or_reuse
        from openwrt_imagegen.profiles.service import profile_to_schema

        # Create existing successful build
        existing_build = BuildRecord(
            profile_id=profile.id,
            imagebuilder_id=imagebuilder.id,
            cache_key="sha256:testkey",
            status=BuildStatus.SUCCEEDED.value,
        )
        session.add(existing_build)
        session.commit()

        profile_schema = profile_to_schema(profile)

        with patch(
            "openwrt_imagegen.builds.service.compute_cache_key_from_profile"
        ) as mock_cache_key:
            mock_inputs = MagicMock()
            mock_inputs.to_dict.return_value = {}
            mock_cache_key.return_value = ("sha256:testkey", mock_inputs)

            with patch(
                "openwrt_imagegen.builds.service.has_overlay_content"
            ) as mock_overlay:
                mock_overlay.return_value = False

                with patch("openwrt_imagegen.builds.service.run_build") as mock_run:
                    mock_result = MagicMock()
                    mock_result.success = True
                    mock_result.bin_dir = tmp_path / "bin"
                    mock_result.bin_dir.mkdir()
                    mock_result.log_path = tmp_path / "build.log"
                    mock_result.log_path.touch()
                    mock_run.return_value = mock_result

                    with patch(
                        "openwrt_imagegen.builds.service.discover_artifacts"
                    ) as mock_discover:
                        mock_discover.return_value = []

                        result, is_cache_hit = build_or_reuse(
                            session=session,
                            profile=profile,
                            profile_schema=profile_schema,
                            imagebuilder=imagebuilder,
                            settings=mock_settings,
                            force_rebuild=True,
                        )

                        # Should not be cache hit, should have run build
                        assert is_cache_hit is False
                        assert mock_run.called
