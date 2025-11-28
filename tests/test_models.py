"""Tests for ORM models and CRUD operations.

These tests verify the database models, relationships, and basic
CRUD operations using an in-memory SQLite database.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from openwrt_imagegen.builds.models import Artifact, BuildRecord
from openwrt_imagegen.db import Base, create_all_tables, get_engine, get_session
from openwrt_imagegen.flash.models import FlashRecord
from openwrt_imagegen.imagebuilder.models import ImageBuilder
from openwrt_imagegen.profiles.models import Profile
from openwrt_imagegen.types import (
    BuildStatus,
    FlashStatus,
    ImageBuilderState,
    VerificationMode,
    VerificationResult,
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


class TestDatabaseSetup:
    """Test database setup and helpers."""

    def test_get_engine(self, tmp_path):
        """get_engine should create an engine from settings."""
        db_path = tmp_path / "test.db"
        engine = get_engine(f"sqlite:///{db_path}")
        assert engine is not None

    def test_create_all_tables(self, tmp_path):
        """create_all_tables should create all model tables."""
        db_path = tmp_path / "test.db"
        engine = get_engine(f"sqlite:///{db_path}")
        create_all_tables(engine)
        # Verify tables exist by checking metadata
        assert "profiles" in Base.metadata.tables
        assert "imagebuilders" in Base.metadata.tables
        assert "build_records" in Base.metadata.tables
        assert "artifacts" in Base.metadata.tables
        assert "flash_records" in Base.metadata.tables

    def test_get_session_context_manager(self, tmp_path):
        """get_session should provide a working session context."""
        db_path = tmp_path / "test.db"
        engine = get_engine(f"sqlite:///{db_path}")
        create_all_tables(engine)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

        with get_session(factory) as session:
            profile = Profile(
                profile_id="test-profile",
                name="Test Profile",
                device_id="test-device",
                openwrt_release="23.05.3",
                target="ath79",
                subtarget="generic",
                imagebuilder_profile="tl-wdr4300-v1",
            )
            session.add(profile)

        # Verify data was committed
        with get_session(factory) as session:
            result = session.query(Profile).filter_by(profile_id="test-profile").first()
            assert result is not None
            assert result.name == "Test Profile"


class TestProfileModel:
    """Test Profile model CRUD operations."""

    def test_create_profile_minimal(self, session):
        """Should create a profile with minimal required fields."""
        profile = Profile(
            profile_id="test-router-1",
            name="Test Router Profile",
            device_id="tl-wdr4300-v1",
            openwrt_release="23.05.3",
            target="ath79",
            subtarget="generic",
            imagebuilder_profile="tl-wdr4300-v1",
        )
        session.add(profile)
        session.commit()

        assert profile.id is not None
        assert profile.profile_id == "test-router-1"
        assert profile.created_at is not None

    def test_create_profile_full(self, session):
        """Should create a profile with all fields."""
        profile = Profile(
            profile_id="test-router-full",
            name="Full Test Profile",
            description="A complete test profile with all fields",
            device_id="tl-wdr4300-v1",
            tags=["test", "router", "wifi"],
            openwrt_release="23.05.3",
            target="ath79",
            subtarget="generic",
            imagebuilder_profile="tl-wdr4300-v1",
            packages=["luci", "luci-app-sqm", "-ppp"],
            packages_remove=["ppp", "ppp-mod-pppoe"],
            files=[{"source": "banner.txt", "destination": "/etc/banner"}],
            overlay_dir="overlays/router1",
            policies={"filesystem": "squashfs", "strip_debug": True},
            build_defaults={"rebuild_if_cached": False},
            bin_dir="/custom/output",
            extra_image_name="custom",
            disabled_services=["dropbear"],
            rootfs_partsize=256,
            add_local_key=True,
            created_by="test_user",
            notes="Test notes",
        )
        session.add(profile)
        session.commit()

        result = session.query(Profile).filter_by(profile_id="test-router-full").first()
        assert result is not None
        assert result.description == "A complete test profile with all fields"
        assert result.tags == ["test", "router", "wifi"]
        assert result.packages == ["luci", "luci-app-sqm", "-ppp"]
        assert result.policies == {"filesystem": "squashfs", "strip_debug": True}
        assert result.rootfs_partsize == 256
        assert result.add_local_key is True

    def test_read_profile(self, session):
        """Should read a profile by profile_id."""
        profile = Profile(
            profile_id="read-test",
            name="Read Test",
            device_id="device-1",
            openwrt_release="23.05.3",
            target="ath79",
            subtarget="generic",
            imagebuilder_profile="device-1",
        )
        session.add(profile)
        session.commit()

        result = session.query(Profile).filter_by(profile_id="read-test").first()
        assert result is not None
        assert result.name == "Read Test"
        assert result.openwrt_release == "23.05.3"

    def test_update_profile(self, session):
        """Should update a profile."""
        profile = Profile(
            profile_id="update-test",
            name="Original Name",
            device_id="device-1",
            openwrt_release="23.05.3",
            target="ath79",
            subtarget="generic",
            imagebuilder_profile="device-1",
        )
        session.add(profile)
        session.commit()

        profile.name = "Updated Name"
        profile.packages = ["luci"]
        session.commit()

        result = session.query(Profile).filter_by(profile_id="update-test").first()
        assert result is not None
        assert result.name == "Updated Name"
        assert result.packages == ["luci"]

    def test_delete_profile(self, session):
        """Should delete a profile."""
        profile = Profile(
            profile_id="delete-test",
            name="To Delete",
            device_id="device-1",
            openwrt_release="23.05.3",
            target="ath79",
            subtarget="generic",
            imagebuilder_profile="device-1",
        )
        session.add(profile)
        session.commit()

        session.delete(profile)
        session.commit()

        result = session.query(Profile).filter_by(profile_id="delete-test").first()
        assert result is None

    def test_profile_unique_profile_id(self, session):
        """Should enforce unique profile_id constraint."""
        profile1 = Profile(
            profile_id="unique-test",
            name="First",
            device_id="device-1",
            openwrt_release="23.05.3",
            target="ath79",
            subtarget="generic",
            imagebuilder_profile="device-1",
        )
        session.add(profile1)
        session.commit()

        profile2 = Profile(
            profile_id="unique-test",  # Duplicate
            name="Second",
            device_id="device-2",
            openwrt_release="23.05.3",
            target="ath79",
            subtarget="generic",
            imagebuilder_profile="device-2",
        )
        session.add(profile2)

        with pytest.raises(IntegrityError):
            session.commit()

    def test_profile_repr(self, session):
        """Should have a useful repr."""
        profile = Profile(
            profile_id="repr-test",
            name="Repr Test",
            device_id="device-1",
            openwrt_release="23.05.3",
            target="ath79",
            subtarget="generic",
            imagebuilder_profile="device-1",
        )
        session.add(profile)
        session.commit()

        repr_str = repr(profile)
        assert "Profile" in repr_str
        assert "repr-test" in repr_str


class TestImageBuilderModel:
    """Test ImageBuilder model CRUD operations."""

    def test_create_imagebuilder(self, session):
        """Should create an ImageBuilder record."""
        builder = ImageBuilder(
            openwrt_release="23.05.3",
            target="ath79",
            subtarget="generic",
            upstream_url="https://downloads.openwrt.org/releases/23.05.3/targets/ath79/generic/openwrt-imagebuilder-23.05.3-ath79-generic.Linux-x86_64.tar.xz",
            root_dir="/cache/builders/23.05.3/ath79/generic",
            checksum="abc123def456",
            signature_verified=True,
            state=ImageBuilderState.READY.value,
        )
        session.add(builder)
        session.commit()

        assert builder.id is not None
        assert builder.state == "ready"
        assert builder.signature_verified is True

    def test_imagebuilder_unique_release_target(self, session):
        """Should enforce unique (release, target, subtarget) constraint."""
        builder1 = ImageBuilder(
            openwrt_release="23.05.3",
            target="ath79",
            subtarget="generic",
            upstream_url="https://example.com/1",
            root_dir="/cache/1",
        )
        session.add(builder1)
        session.commit()

        builder2 = ImageBuilder(
            openwrt_release="23.05.3",
            target="ath79",
            subtarget="generic",  # Duplicate
            upstream_url="https://example.com/2",
            root_dir="/cache/2",
        )
        session.add(builder2)

        with pytest.raises(IntegrityError):
            session.commit()

    def test_imagebuilder_state_methods(self, session):
        """Should have working state transition methods."""
        builder = ImageBuilder(
            openwrt_release="23.05.3",
            target="ramips",
            subtarget="mt7621",
            upstream_url="https://example.com/",
            root_dir="/cache/test",
        )
        session.add(builder)
        session.commit()

        assert builder.state == ImageBuilderState.PENDING.value
        assert not builder.is_ready()

        builder.mark_ready()
        session.commit()
        assert builder.state == ImageBuilderState.READY.value
        assert builder.is_ready()

        builder.mark_broken()
        session.commit()
        assert builder.state == ImageBuilderState.BROKEN.value

        builder.mark_deprecated()
        session.commit()
        assert builder.state == ImageBuilderState.DEPRECATED.value

    def test_imagebuilder_repr(self, session):
        """Should have a useful repr."""
        builder = ImageBuilder(
            openwrt_release="23.05.3",
            target="x86",
            subtarget="64",
            upstream_url="https://example.com/",
            root_dir="/cache/test",
        )
        session.add(builder)
        session.commit()

        repr_str = repr(builder)
        assert "ImageBuilder" in repr_str
        assert "23.05.3" in repr_str


class TestBuildRecordModel:
    """Test BuildRecord model CRUD operations."""

    @pytest.fixture
    def profile_and_builder(self, session):
        """Create a profile and builder for build tests."""
        profile = Profile(
            profile_id="build-test-profile",
            name="Build Test Profile",
            device_id="device-1",
            openwrt_release="23.05.3",
            target="ath79",
            subtarget="generic",
            imagebuilder_profile="device-1",
        )
        builder = ImageBuilder(
            openwrt_release="23.05.3",
            target="ath79",
            subtarget="generic",
            upstream_url="https://example.com/",
            root_dir="/cache/test",
            state=ImageBuilderState.READY.value,
        )
        session.add_all([profile, builder])
        session.commit()
        return profile, builder

    def test_create_build_record(self, session, profile_and_builder):
        """Should create a BuildRecord."""
        profile, builder = profile_and_builder

        build = BuildRecord(
            profile_id=profile.id,
            imagebuilder_id=builder.id,
            cache_key="sha256:abc123",
            input_snapshot={"profile": "build-test-profile", "packages": ["luci"]},
        )
        session.add(build)
        session.commit()

        assert build.id is not None
        assert build.status == BuildStatus.PENDING.value
        assert build.requested_at is not None

    def test_build_record_status_methods(self, session, profile_and_builder):
        """Should have working status transition methods."""
        profile, builder = profile_and_builder

        build = BuildRecord(
            profile_id=profile.id,
            imagebuilder_id=builder.id,
            cache_key="sha256:test123",
        )
        session.add(build)
        session.commit()

        assert build.status == BuildStatus.PENDING.value

        build.mark_running()
        session.commit()
        assert build.status == BuildStatus.RUNNING.value
        assert build.started_at is not None

        build.mark_succeeded()
        session.commit()
        assert build.status == BuildStatus.SUCCEEDED.value
        assert build.finished_at is not None
        assert build.is_succeeded()

    def test_build_record_failure(self, session, profile_and_builder):
        """Should record build failures properly."""
        profile, builder = profile_and_builder

        build = BuildRecord(
            profile_id=profile.id,
            imagebuilder_id=builder.id,
            cache_key="sha256:fail123",
        )
        session.add(build)
        session.commit()

        build.mark_running()
        build.mark_failed(error_type="build_error", message="Package not found")
        session.commit()

        assert build.status == BuildStatus.FAILED.value
        assert build.error_type == "build_error"
        assert build.error_message == "Package not found"
        assert not build.is_succeeded()

    def test_build_record_relationships(self, session, profile_and_builder):
        """Should have working relationships."""
        profile, builder = profile_and_builder

        build = BuildRecord(
            profile_id=profile.id,
            imagebuilder_id=builder.id,
            cache_key="sha256:rel123",
        )
        session.add(build)
        session.commit()

        # Access relationships
        assert build.profile == profile
        assert build.imagebuilder == builder

        # Access reverse relationships
        assert build in list(profile.builds)
        assert build in list(builder.builds)


class TestArtifactModel:
    """Test Artifact model CRUD operations."""

    @pytest.fixture
    def build_record(self, session):
        """Create a build record for artifact tests."""
        profile = Profile(
            profile_id="artifact-test-profile",
            name="Artifact Test",
            device_id="device-1",
            openwrt_release="23.05.3",
            target="ath79",
            subtarget="generic",
            imagebuilder_profile="device-1",
        )
        builder = ImageBuilder(
            openwrt_release="23.05.3",
            target="ath79",
            subtarget="generic",
            upstream_url="https://example.com/",
            root_dir="/cache/test",
        )
        session.add_all([profile, builder])
        session.commit()

        build = BuildRecord(
            profile_id=profile.id,
            imagebuilder_id=builder.id,
            cache_key="sha256:artifact123",
            status=BuildStatus.SUCCEEDED.value,
        )
        session.add(build)
        session.commit()
        return build

    def test_create_artifact(self, session, build_record):
        """Should create an Artifact."""
        artifact = Artifact(
            build_id=build_record.id,
            kind="sysupgrade",
            relative_path="23.05.3/ath79/generic/openwrt-sysupgrade.bin",
            filename="openwrt-sysupgrade.bin",
            size_bytes=10485760,
            sha256="abc123def456789",
            labels=["for_tf_flash"],
        )
        session.add(artifact)
        session.commit()

        assert artifact.id is not None
        assert artifact.kind == "sysupgrade"
        assert artifact.size_bytes == 10485760

    def test_artifact_relationship(self, session, build_record):
        """Should have working relationship to build."""
        artifact = Artifact(
            build_id=build_record.id,
            kind="factory",
            relative_path="image.bin",
            filename="image.bin",
            size_bytes=1024,
            sha256="test123",
        )
        session.add(artifact)
        session.commit()

        assert artifact.build == build_record
        assert artifact in build_record.artifacts

    def test_artifact_repr(self, session, build_record):
        """Should have a useful repr."""
        artifact = Artifact(
            build_id=build_record.id,
            kind="manifest",
            relative_path="manifest.json",
            filename="manifest.json",
            size_bytes=512,
            sha256="manifest123",
        )
        session.add(artifact)
        session.commit()

        repr_str = repr(artifact)
        assert "Artifact" in repr_str
        assert "manifest.json" in repr_str


class TestFlashRecordModel:
    """Test FlashRecord model CRUD operations."""

    @pytest.fixture
    def artifact(self, session):
        """Create an artifact for flash tests."""
        profile = Profile(
            profile_id="flash-test-profile",
            name="Flash Test",
            device_id="device-1",
            openwrt_release="23.05.3",
            target="ath79",
            subtarget="generic",
            imagebuilder_profile="device-1",
        )
        builder = ImageBuilder(
            openwrt_release="23.05.3",
            target="ath79",
            subtarget="generic",
            upstream_url="https://example.com/",
            root_dir="/cache/test",
        )
        session.add_all([profile, builder])
        session.commit()

        build = BuildRecord(
            profile_id=profile.id,
            imagebuilder_id=builder.id,
            cache_key="sha256:flash123",
            status=BuildStatus.SUCCEEDED.value,
        )
        session.add(build)
        session.commit()

        artifact = Artifact(
            build_id=build.id,
            kind="sysupgrade",
            relative_path="image.bin",
            filename="image.bin",
            size_bytes=10485760,
            sha256="flash_artifact_hash",
        )
        session.add(artifact)
        session.commit()
        return artifact

    def test_create_flash_record(self, session, artifact):
        """Should create a FlashRecord."""
        flash = FlashRecord(
            artifact_id=artifact.id,
            build_id=artifact.build_id,
            device_path="/dev/sdc",
            device_model="SD Card Reader",
            device_serial="ABC123",
            verification_mode=VerificationMode.FULL.value,
        )
        session.add(flash)
        session.commit()

        assert flash.id is not None
        assert flash.status == FlashStatus.PENDING.value
        assert flash.device_path == "/dev/sdc"

    def test_flash_record_status_methods(self, session, artifact):
        """Should have working status transition methods."""
        flash = FlashRecord(
            artifact_id=artifact.id,
            build_id=artifact.build_id,
            device_path="/dev/sdd",
        )
        session.add(flash)
        session.commit()

        flash.mark_running()
        session.commit()
        assert flash.status == FlashStatus.RUNNING.value
        assert flash.started_at is not None

        flash.verification_result = VerificationResult.MATCH.value
        flash.mark_succeeded()
        session.commit()

        assert flash.status == FlashStatus.SUCCEEDED.value
        assert flash.is_succeeded()

    def test_flash_record_failure(self, session, artifact):
        """Should record flash failures properly."""
        flash = FlashRecord(
            artifact_id=artifact.id,
            build_id=artifact.build_id,
            device_path="/dev/sde",
        )
        session.add(flash)
        session.commit()

        flash.mark_running()
        flash.mark_failed(error_type="write_error", message="Device read-only")
        session.commit()

        assert flash.status == FlashStatus.FAILED.value
        assert flash.error_type == "write_error"
        assert not flash.is_succeeded()

    def test_flash_record_relationships(self, session, artifact):
        """Should have working relationships."""
        flash = FlashRecord(
            artifact_id=artifact.id,
            build_id=artifact.build_id,
            device_path="/dev/sdf",
        )
        session.add(flash)
        session.commit()

        assert flash.artifact == artifact
        assert flash.build == artifact.build
        assert flash in list(artifact.flash_records)


class TestQueryPatterns:
    """Test common query patterns described in DB_MODELS.md."""

    @pytest.fixture
    def populated_db(self, session):
        """Create a populated database for query tests."""
        # Create multiple profiles
        profiles = []
        for i in range(3):
            profile = Profile(
                profile_id=f"query-profile-{i}",
                name=f"Query Profile {i}",
                device_id=f"device-{i % 2}",  # 0, 1, 0
                tags=["tag-a"] if i % 2 == 0 else ["tag-b"],
                openwrt_release="23.05.3" if i < 2 else "22.03.5",
                target="ath79",
                subtarget="generic",
                imagebuilder_profile=f"device-{i}",
            )
            profiles.append(profile)

        # Create builders
        builders = [
            ImageBuilder(
                openwrt_release="23.05.3",
                target="ath79",
                subtarget="generic",
                upstream_url="https://example.com/1",
                root_dir="/cache/1",
                state=ImageBuilderState.READY.value,
            ),
            ImageBuilder(
                openwrt_release="22.03.5",
                target="ath79",
                subtarget="generic",
                upstream_url="https://example.com/2",
                root_dir="/cache/2",
                state=ImageBuilderState.READY.value,
            ),
        ]

        session.add_all(profiles + builders)
        session.commit()
        return {"profiles": profiles, "builders": builders}

    def test_query_profiles_by_release(self, session, populated_db):
        """Should query profiles by OpenWrt release."""
        _ = populated_db  # Fixture populates database
        results = session.query(Profile).filter_by(openwrt_release="23.05.3").all()
        assert len(results) == 2

    def test_query_profiles_by_device_id(self, session, populated_db):
        """Should query profiles by device_id."""
        _ = populated_db  # Fixture populates database
        results = session.query(Profile).filter_by(device_id="device-0").all()
        assert len(results) == 2

    def test_query_imagebuilder_by_target(self, session, populated_db):
        """Should query ImageBuilder by (release, target, subtarget)."""
        _ = populated_db  # Fixture populates database
        result = (
            session.query(ImageBuilder)
            .filter_by(openwrt_release="23.05.3", target="ath79", subtarget="generic")
            .first()
        )
        assert result is not None
        assert result.state == ImageBuilderState.READY.value

    def test_query_latest_successful_build(self, session, populated_db):
        """Should query latest successful build for a profile."""
        profiles = populated_db["profiles"]
        builders = populated_db["builders"]

        # Create some builds
        for i, status in enumerate(
            [BuildStatus.SUCCEEDED, BuildStatus.FAILED, BuildStatus.SUCCEEDED]
        ):
            build = BuildRecord(
                profile_id=profiles[0].id,
                imagebuilder_id=builders[0].id,
                cache_key=f"key-{i}",
                status=status.value,
            )
            session.add(build)

        session.commit()

        # Query latest successful build
        latest = (
            session.query(BuildRecord)
            .filter_by(profile_id=profiles[0].id, status=BuildStatus.SUCCEEDED.value)
            .order_by(BuildRecord.id.desc())
            .first()
        )

        assert latest is not None
        assert latest.cache_key == "key-2"
