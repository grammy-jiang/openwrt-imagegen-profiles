"""Tests for Image Builder service module.

These tests verify the high-level Image Builder management APIs
including ensure_builder, list_builders, prune_builders, and locking.
"""

import hashlib
import lzma
import tarfile
import threading
import time
from io import BytesIO
from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from openwrt_imagegen.db import Base
from openwrt_imagegen.imagebuilder.fetch import OPENWRT_DOWNLOAD_BASE
from openwrt_imagegen.imagebuilder.models import ImageBuilder
from openwrt_imagegen.imagebuilder.service import (
    ImageBuilderBrokenError,
    ImageBuilderNotFoundError,
    OfflineModeError,
    builder_lock,
    ensure_builder,
    get_builder,
    get_builder_cache_info,
    list_builders,
    prune_builders,
)
from openwrt_imagegen.types import ImageBuilderState


@pytest.fixture
def engine():
    """Create an in-memory SQLite engine for testing."""
    # Import all models to ensure they are registered with SQLAlchemy's mapper
    from openwrt_imagegen.builds import models as builds_models  # noqa: F401
    from openwrt_imagegen.flash import models as flash_models  # noqa: F401
    from openwrt_imagegen.profiles import models as profiles_models  # noqa: F401

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
def mock_settings(tmp_path):
    """Create mock settings with temp directories."""
    from openwrt_imagegen.config import Settings

    return Settings(
        cache_dir=tmp_path / "cache",
        artifacts_dir=tmp_path / "artifacts",
        db_url="sqlite:///:memory:",
        offline=False,
    )


def create_mock_archive(name: str) -> tuple[str, bytes]:
    """Create a mock .tar.xz archive and return checksum and content."""
    tar_bytes = BytesIO()
    with tarfile.open(fileobj=tar_bytes, mode="w") as tar:
        info = tarfile.TarInfo(name=f"{name}/Makefile")
        content = b"# Mock Makefile"
        info.size = len(content)
        tar.addfile(info, BytesIO(content))

    tar_bytes.seek(0)
    xz_content = lzma.compress(tar_bytes.read())
    checksum = hashlib.sha256(xz_content).hexdigest()

    return checksum, xz_content


class TestBuilderLock:
    """Tests for builder_lock context manager."""

    def test_lock_creates_lock_file(self, tmp_path):
        """Should create lock file in .locks directory."""
        with builder_lock(tmp_path, "23.05.3", "ath79", "generic"):
            lock_dir = tmp_path / ".locks"
            assert lock_dir.exists()
            lock_files = list(lock_dir.glob("*.lock"))
            assert len(lock_files) == 1

    def test_lock_is_exclusive(self, tmp_path):
        """Should prevent concurrent access."""
        results: list[str] = []

        def worker(worker_id: int) -> None:
            with builder_lock(tmp_path, "23.05.3", "ath79", "generic"):
                results.append(f"start-{worker_id}")
                time.sleep(0.1)
                results.append(f"end-{worker_id}")

        thread1 = threading.Thread(target=worker, args=(1,))
        thread2 = threading.Thread(target=worker, args=(2,))

        thread1.start()
        time.sleep(0.01)  # Give thread1 time to acquire lock
        thread2.start()

        thread1.join()
        thread2.join()

        # Workers should have executed sequentially, not interleaved
        assert results == ["start-1", "end-1", "start-2", "end-2"] or results == [
            "start-2",
            "end-2",
            "start-1",
            "end-1",
        ]

    def test_lock_with_timeout(self, tmp_path):
        """Should timeout when lock cannot be acquired."""
        acquired = threading.Event()
        released = threading.Event()

        def holder() -> None:
            with builder_lock(tmp_path, "23.05.3", "ath79", "generic"):
                acquired.set()
                released.wait(timeout=5)

        holder_thread = threading.Thread(target=holder)
        holder_thread.start()
        acquired.wait(timeout=1)

        try:
            with (
                pytest.raises(TimeoutError),
                builder_lock(tmp_path, "23.05.3", "ath79", "generic", timeout=0.1),
            ):
                pass
        finally:
            released.set()
            holder_thread.join()


class TestGetBuilder:
    """Tests for get_builder function."""

    def test_get_existing_builder(self, session):
        """Should return existing builder."""
        builder = ImageBuilder(
            openwrt_release="23.05.3",
            target="ath79",
            subtarget="generic",
            upstream_url="https://example.com/",
            root_dir="/cache/test",
            state=ImageBuilderState.READY.value,
        )
        session.add(builder)
        session.commit()

        result = get_builder(session, "23.05.3", "ath79", "generic")

        assert result.id == builder.id
        assert result.openwrt_release == "23.05.3"

    def test_get_nonexistent_builder(self, session):
        """Should raise ImageBuilderNotFoundError."""
        with pytest.raises(ImageBuilderNotFoundError) as exc_info:
            get_builder(session, "23.05.3", "ath79", "generic")

        assert exc_info.value.release == "23.05.3"
        assert exc_info.value.target == "ath79"
        assert exc_info.value.subtarget == "generic"


class TestListBuilders:
    """Tests for list_builders function."""

    @pytest.fixture
    def populated_db(self, session):
        """Populate database with test builders."""
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
                openwrt_release="23.05.3",
                target="ramips",
                subtarget="mt7621",
                upstream_url="https://example.com/2",
                root_dir="/cache/2",
                state=ImageBuilderState.READY.value,
            ),
            ImageBuilder(
                openwrt_release="22.03.5",
                target="ath79",
                subtarget="generic",
                upstream_url="https://example.com/3",
                root_dir="/cache/3",
                state=ImageBuilderState.DEPRECATED.value,
            ),
        ]
        session.add_all(builders)
        session.commit()
        return builders

    def test_list_all_builders(self, session, populated_db):  # noqa: ARG002
        """Should list all builders."""
        results = list_builders(session)
        assert len(results) == 3

    def test_list_by_release(self, session, populated_db):  # noqa: ARG002
        """Should filter by release."""
        results = list_builders(session, release="23.05.3")
        assert len(results) == 2

    def test_list_by_target(self, session, populated_db):  # noqa: ARG002
        """Should filter by target."""
        results = list_builders(session, target="ath79")
        assert len(results) == 2

    def test_list_by_state(self, session, populated_db):  # noqa: ARG002
        """Should filter by state."""
        results = list_builders(session, state=ImageBuilderState.DEPRECATED)
        assert len(results) == 1
        assert results[0].openwrt_release == "22.03.5"

    def test_list_combined_filters(self, session, populated_db):  # noqa: ARG002
        """Should apply multiple filters."""
        results = list_builders(session, release="23.05.3", target="ath79")
        assert len(results) == 1
        assert results[0].subtarget == "generic"


class TestEnsureBuilder:
    """Tests for ensure_builder function."""

    @respx.mock
    def test_ensure_downloads_new_builder(self, session, mock_settings):
        """Should download new builder when not cached."""
        archive_name = "openwrt-imagebuilder-23.05.3-ath79-generic.Linux-x86_64"
        checksum, content = create_mock_archive(archive_name)

        respx.get(
            f"{OPENWRT_DOWNLOAD_BASE}/releases/23.05.3/targets/ath79/generic/"
            f"{archive_name}.tar.xz"
        ).mock(return_value=httpx.Response(200, content=content))
        respx.get(
            f"{OPENWRT_DOWNLOAD_BASE}/releases/23.05.3/targets/ath79/generic/sha256sums"
        ).mock(
            return_value=httpx.Response(
                200, text=f"{checksum}  {archive_name}.tar.xz\n"
            )
        )

        result = ensure_builder(
            session,
            release="23.05.3",
            target="ath79",
            subtarget="generic",
            settings=mock_settings,
        )

        assert result.state == ImageBuilderState.READY.value
        assert result.checksum == checksum
        assert Path(result.root_dir).exists()

    def test_ensure_uses_cached_builder(self, session, mock_settings):
        """Should use cached builder when available."""
        # Create a cached builder
        root_dir = (
            mock_settings.cache_dir
            / "23.05.3"
            / "ath79"
            / "generic"
            / "openwrt-imagebuilder"
        )
        root_dir.mkdir(parents=True)
        (root_dir / "Makefile").write_text("# Test")

        builder = ImageBuilder(
            openwrt_release="23.05.3",
            target="ath79",
            subtarget="generic",
            upstream_url="https://example.com/",
            root_dir=str(root_dir),
            state=ImageBuilderState.READY.value,
            checksum="abc123",
        )
        session.add(builder)
        session.commit()

        # Should not make any HTTP requests
        result = ensure_builder(
            session,
            release="23.05.3",
            target="ath79",
            subtarget="generic",
            settings=mock_settings,
        )

        assert result.id == builder.id

    @respx.mock
    def test_ensure_redownloads_missing_directory(self, session, mock_settings):
        """Should re-download if directory was deleted externally."""
        # Create builder record without directory
        builder = ImageBuilder(
            openwrt_release="23.05.3",
            target="ath79",
            subtarget="generic",
            upstream_url="https://example.com/",
            root_dir="/nonexistent/path",
            state=ImageBuilderState.READY.value,
        )
        session.add(builder)
        session.commit()

        archive_name = "openwrt-imagebuilder-23.05.3-ath79-generic.Linux-x86_64"
        checksum, content = create_mock_archive(archive_name)

        respx.get(
            f"{OPENWRT_DOWNLOAD_BASE}/releases/23.05.3/targets/ath79/generic/"
            f"{archive_name}.tar.xz"
        ).mock(return_value=httpx.Response(200, content=content))
        respx.get(
            f"{OPENWRT_DOWNLOAD_BASE}/releases/23.05.3/targets/ath79/generic/sha256sums"
        ).mock(
            return_value=httpx.Response(
                200, text=f"{checksum}  {archive_name}.tar.xz\n"
            )
        )

        result = ensure_builder(
            session,
            release="23.05.3",
            target="ath79",
            subtarget="generic",
            settings=mock_settings,
        )

        assert result.state == ImageBuilderState.READY.value
        assert Path(result.root_dir).exists()

    def test_ensure_raises_on_broken_builder(self, session, mock_settings):
        """Should raise ImageBuilderBrokenError for broken builders."""
        builder = ImageBuilder(
            openwrt_release="23.05.3",
            target="ath79",
            subtarget="generic",
            upstream_url="https://example.com/",
            root_dir="/cache/test",
            state=ImageBuilderState.BROKEN.value,
        )
        session.add(builder)
        session.commit()

        with pytest.raises(ImageBuilderBrokenError):
            ensure_builder(
                session,
                release="23.05.3",
                target="ath79",
                subtarget="generic",
                settings=mock_settings,
            )

    def test_ensure_offline_mode_raises(self, session, mock_settings):
        """Should raise OfflineModeError when offline."""
        mock_settings.offline = True

        with pytest.raises(OfflineModeError):
            ensure_builder(
                session,
                release="23.05.3",
                target="ath79",
                subtarget="generic",
                settings=mock_settings,
            )

    @respx.mock
    def test_ensure_force_download(self, session, mock_settings):
        """Should re-download when force_download=True."""
        # Create a cached builder
        root_dir = (
            mock_settings.cache_dir
            / "23.05.3"
            / "ath79"
            / "generic"
            / "openwrt-imagebuilder"
        )
        root_dir.mkdir(parents=True)
        (root_dir / "Makefile").write_text("# Old")

        builder = ImageBuilder(
            openwrt_release="23.05.3",
            target="ath79",
            subtarget="generic",
            upstream_url="https://example.com/",
            root_dir=str(root_dir),
            state=ImageBuilderState.READY.value,
            checksum="oldchecksum",
        )
        session.add(builder)
        session.commit()

        archive_name = "openwrt-imagebuilder-23.05.3-ath79-generic.Linux-x86_64"
        checksum, content = create_mock_archive(archive_name)

        respx.get(
            f"{OPENWRT_DOWNLOAD_BASE}/releases/23.05.3/targets/ath79/generic/"
            f"{archive_name}.tar.xz"
        ).mock(return_value=httpx.Response(200, content=content))
        respx.get(
            f"{OPENWRT_DOWNLOAD_BASE}/releases/23.05.3/targets/ath79/generic/sha256sums"
        ).mock(
            return_value=httpx.Response(
                200, text=f"{checksum}  {archive_name}.tar.xz\n"
            )
        )

        result = ensure_builder(
            session,
            release="23.05.3",
            target="ath79",
            subtarget="generic",
            settings=mock_settings,
            force_download=True,
        )

        assert result.checksum == checksum


class TestPruneBuilders:
    """Tests for prune_builders function."""

    @pytest.fixture
    def populated_db_with_dirs(self, session, mock_settings):
        """Populate database with builders and create directories."""
        builders = []

        for release, state in [
            ("23.05.3", ImageBuilderState.READY),
            ("22.03.5", ImageBuilderState.DEPRECATED),
            ("21.02.7", ImageBuilderState.DEPRECATED),
        ]:
            root_dir = (
                mock_settings.cache_dir
                / release
                / "ath79"
                / "generic"
                / "openwrt-imagebuilder"
            )
            root_dir.mkdir(parents=True)
            (root_dir / "Makefile").write_text("# Test")

            builder = ImageBuilder(
                openwrt_release=release,
                target="ath79",
                subtarget="generic",
                upstream_url="https://example.com/",
                root_dir=str(root_dir),
                state=state.value,
            )
            builders.append(builder)

        session.add_all(builders)
        session.commit()
        return builders

    def test_prune_deprecated_only(
        self,
        session,
        mock_settings,
        populated_db_with_dirs,  # noqa: ARG002
    ):
        """Should prune only deprecated builders by default."""
        pruned = prune_builders(session, settings=mock_settings)

        assert len(pruned) == 2
        assert ("22.03.5", "ath79", "generic") in pruned
        assert ("21.02.7", "ath79", "generic") in pruned

        # Verify DB state
        remaining = list_builders(session)
        assert len(remaining) == 1
        assert remaining[0].openwrt_release == "23.05.3"

    def test_prune_dry_run(self, session, mock_settings, populated_db_with_dirs):
        """Should not actually prune in dry-run mode."""
        pruned = prune_builders(session, settings=mock_settings, dry_run=True)

        assert len(pruned) == 2

        # Verify nothing was actually deleted
        remaining = list_builders(session)
        assert len(remaining) == 3

        # Verify directories still exist
        for builder in populated_db_with_dirs:
            if builder.state == ImageBuilderState.DEPRECATED.value:
                assert Path(builder.root_dir).exists()

    def test_prune_mutually_exclusive_options(self, session, mock_settings):
        """Should raise ValueError when both deprecated_only and unused_days are specified."""
        with pytest.raises(ValueError) as exc_info:
            prune_builders(
                session,
                deprecated_only=True,
                unused_days=30,
                settings=mock_settings,
            )

        assert "Cannot specify both" in str(exc_info.value)


class TestGetBuilderCacheInfo:
    """Tests for get_builder_cache_info function."""

    def test_cache_info_empty(self, mock_settings):
        """Should return info for empty cache."""
        info = get_builder_cache_info(mock_settings)

        assert info["cache_dir"] == str(mock_settings.cache_dir)
        assert info["total_size_bytes"] == 0
        assert info["exists"] is False

    def test_cache_info_with_files(self, mock_settings):
        """Should return correct size for cache with files."""
        mock_settings.cache_dir.mkdir(parents=True)
        (mock_settings.cache_dir / "file.bin").write_bytes(b"A" * 1000)

        info = get_builder_cache_info(mock_settings)

        assert info["total_size_bytes"] == 1000
        assert info["exists"] is True


class TestErrorClasses:
    """Tests for error classes."""

    def test_imagebuilder_not_found_error(self):
        """Should contain release/target/subtarget info."""
        error = ImageBuilderNotFoundError("23.05.3", "ath79", "generic")

        assert error.release == "23.05.3"
        assert error.target == "ath79"
        assert error.subtarget == "generic"
        assert error.code == "imagebuilder_not_found"
        assert "23.05.3" in str(error)

    def test_imagebuilder_broken_error(self):
        """Should contain release/target/subtarget info."""
        error = ImageBuilderBrokenError("23.05.3", "ath79", "generic")

        assert error.release == "23.05.3"
        assert error.code == "imagebuilder_broken"

    def test_offline_mode_error(self):
        """Should have default message and code."""
        error = OfflineModeError()

        assert error.code == "offline_mode"
        assert "offline" in str(error).lower()
