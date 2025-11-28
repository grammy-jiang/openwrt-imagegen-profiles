"""Tests for builds/overlay.py module.

Tests overlay staging, hashing, and file manipulation.
"""

import stat

import pytest

from openwrt_imagegen.builds.overlay import (
    OverlayStagingError,
    compute_tree_hash,
    has_overlay_content,
    parse_mode,
    stage_and_hash_overlay,
    stage_directory,
    stage_file,
    stage_overlay,
)
from openwrt_imagegen.profiles.schema import FileSpecSchema, ProfileSchema


@pytest.fixture
def minimal_profile() -> ProfileSchema:
    """Create a minimal valid profile schema."""
    return ProfileSchema(
        profile_id="test.overlay",
        name="Overlay Test",
        device_id="overlay-device",
        openwrt_release="23.05.3",
        target="ath79",
        subtarget="generic",
        imagebuilder_profile="overlay-profile",
    )


class TestParseMode:
    """Tests for parse_mode function."""

    def test_octal_with_leading_zero(self):
        """Should parse mode with leading zero."""
        assert parse_mode("0644") == 0o644
        assert parse_mode("0755") == 0o755
        assert parse_mode("0600") == 0o600

    def test_octal_without_leading_zero(self):
        """Should parse mode without leading zero."""
        assert parse_mode("644") == 0o644
        assert parse_mode("755") == 0o755

    def test_none_returns_none(self):
        """Should return None for None input."""
        assert parse_mode(None) is None

    def test_empty_string_returns_none(self):
        """Should return None for empty string."""
        assert parse_mode("") is None

    def test_invalid_mode_returns_none(self):
        """Should return None for invalid mode."""
        assert parse_mode("invalid") is None
        assert parse_mode("999") is None  # 9 is not valid octal


class TestStageFile:
    """Tests for stage_file function."""

    def test_stage_simple_file(self, tmp_path):
        """Should copy file to destination."""
        # Create source file
        source = tmp_path / "source" / "test.txt"
        source.parent.mkdir(parents=True)
        source.write_text("test content")

        # Stage to destination
        dest = tmp_path / "staging" / "etc" / "test.txt"
        stage_file(source, dest)

        assert dest.exists()
        assert dest.read_text() == "test content"

    def test_stage_with_mode(self, tmp_path):
        """Should apply specified mode."""
        source = tmp_path / "source.txt"
        source.write_text("test")

        dest = tmp_path / "dest.txt"
        stage_file(source, dest, mode=0o600)

        assert dest.exists()
        assert stat.S_IMODE(dest.stat().st_mode) == 0o600

    def test_creates_parent_directories(self, tmp_path):
        """Should create parent directories."""
        source = tmp_path / "source.txt"
        source.write_text("test")

        dest = tmp_path / "deep" / "nested" / "path" / "dest.txt"
        stage_file(source, dest)

        assert dest.exists()
        assert dest.read_text() == "test"

    def test_source_not_found_raises(self, tmp_path):
        """Should raise for missing source."""
        source = tmp_path / "nonexistent.txt"
        dest = tmp_path / "dest.txt"

        with pytest.raises(OverlayStagingError) as exc_info:
            stage_file(source, dest)

        assert "file_stage_error" in exc_info.value.code


class TestStageDirectory:
    """Tests for stage_directory function."""

    def test_stage_directory_tree(self, tmp_path):
        """Should copy entire directory tree."""
        # Create source tree
        source_dir = tmp_path / "source"
        (source_dir / "etc").mkdir(parents=True)
        (source_dir / "etc" / "config").mkdir()
        (source_dir / "etc" / "banner").write_text("Welcome!")
        (source_dir / "etc" / "config" / "network").write_text("network config")

        # Stage
        dest_dir = tmp_path / "staging"
        stage_directory(source_dir, dest_dir)

        assert (dest_dir / "etc" / "banner").exists()
        assert (dest_dir / "etc" / "banner").read_text() == "Welcome!"
        assert (dest_dir / "etc" / "config" / "network").exists()

    def test_stage_empty_directory(self, tmp_path):
        """Should handle empty directory without error."""
        source_dir = tmp_path / "empty"
        source_dir.mkdir()

        dest_dir = tmp_path / "staging"
        # Function doesn't create dest_dir for empty source (no files to stage)
        # This is expected behavior - just verify no error occurs
        stage_directory(source_dir, dest_dir)

        # dest_dir won't exist since there was nothing to stage
        # This is correct behavior - we don't create empty dirs

    def test_symlink_within_tree_allowed(self, tmp_path):
        """Should handle symlinks pointing within source tree."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "real.txt").write_text("real content")
        (source_dir / "link.txt").symlink_to(source_dir / "real.txt")

        dest_dir = tmp_path / "staging"
        stage_directory(source_dir, dest_dir)

        # Symlink should be copied as regular file with resolved content
        assert (dest_dir / "link.txt").exists()
        assert (dest_dir / "link.txt").read_text() == "real content"

    def test_symlink_escape_blocked(self, tmp_path):
        """Should block symlinks pointing outside source tree."""
        # Create external file
        external = tmp_path / "external.txt"
        external.write_text("external content")

        # Create source with symlink to external
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "escape.txt").symlink_to(external)

        dest_dir = tmp_path / "staging"

        with pytest.raises(OverlayStagingError) as exc_info:
            stage_directory(source_dir, dest_dir)

        assert "symlink_escape" in exc_info.value.code


class TestHasOverlayContent:
    """Tests for has_overlay_content function."""

    def test_no_overlay(self, minimal_profile):
        """Should return False for profile without overlay."""
        assert has_overlay_content(minimal_profile) is False

    def test_with_files(self, minimal_profile):
        """Should return True for profile with files."""
        profile = ProfileSchema(
            **{
                **minimal_profile.model_dump(),
                "files": [
                    FileSpecSchema(source="test.txt", destination="/etc/test.txt")
                ],
            }
        )
        assert has_overlay_content(profile) is True

    def test_with_overlay_dir(self, minimal_profile):
        """Should return True for profile with overlay_dir."""
        profile = ProfileSchema(
            **{
                **minimal_profile.model_dump(),
                "overlay_dir": "overlays/test",
            }
        )
        assert has_overlay_content(profile) is True


class TestStageOverlay:
    """Tests for stage_overlay function."""

    def test_stage_from_files(self, tmp_path, minimal_profile):
        """Should stage files from profile."""
        # Create source file
        base_path = tmp_path / "base"
        (base_path / "files").mkdir(parents=True)
        (base_path / "files" / "banner").write_text("Custom banner")

        # Create profile with files
        profile = ProfileSchema(
            **{
                **minimal_profile.model_dump(),
                "files": [
                    FileSpecSchema(
                        source="files/banner",
                        destination="/etc/banner",
                        mode="0644",
                    )
                ],
            }
        )

        staging_dir = tmp_path / "staging"
        result = stage_overlay(staging_dir, profile, base_path)

        assert result == staging_dir
        assert (staging_dir / "etc" / "banner").exists()
        assert (staging_dir / "etc" / "banner").read_text() == "Custom banner"

    def test_stage_from_overlay_dir(self, tmp_path, minimal_profile):
        """Should stage overlay_dir content."""
        # Create overlay directory
        base_path = tmp_path / "base"
        overlay_dir = base_path / "overlays" / "test"
        (overlay_dir / "etc").mkdir(parents=True)
        (overlay_dir / "etc" / "config").write_text("config content")

        # Create profile with overlay_dir
        profile = ProfileSchema(
            **{
                **minimal_profile.model_dump(),
                "overlay_dir": "overlays/test",
            }
        )

        staging_dir = tmp_path / "staging"
        stage_overlay(staging_dir, profile, base_path)

        assert (staging_dir / "etc" / "config").exists()
        assert (staging_dir / "etc" / "config").read_text() == "config content"

    def test_files_override_overlay_dir(self, tmp_path, minimal_profile):
        """Files should override overlay_dir content."""
        base_path = tmp_path / "base"

        # Create overlay_dir with banner
        overlay_dir = base_path / "overlays" / "test"
        (overlay_dir / "etc").mkdir(parents=True)
        (overlay_dir / "etc" / "banner").write_text("overlay banner")

        # Create file that overrides
        (base_path / "files").mkdir()
        (base_path / "files" / "banner").write_text("file banner")

        # Create profile with both
        profile = ProfileSchema(
            **{
                **minimal_profile.model_dump(),
                "overlay_dir": "overlays/test",
                "files": [
                    FileSpecSchema(
                        source="files/banner",
                        destination="/etc/banner",
                    )
                ],
            }
        )

        staging_dir = tmp_path / "staging"
        stage_overlay(staging_dir, profile, base_path)

        # File should win
        assert (staging_dir / "etc" / "banner").read_text() == "file banner"

    def test_missing_overlay_dir_raises(self, tmp_path, minimal_profile):
        """Should raise for missing overlay_dir."""
        profile = ProfileSchema(
            **{
                **minimal_profile.model_dump(),
                "overlay_dir": "nonexistent/path",
            }
        )

        staging_dir = tmp_path / "staging"
        with pytest.raises(OverlayStagingError) as exc_info:
            stage_overlay(staging_dir, profile, tmp_path)

        assert "overlay_not_found" in exc_info.value.code

    def test_missing_source_file_raises(self, tmp_path, minimal_profile):
        """Should raise for missing source file."""
        profile = ProfileSchema(
            **{
                **minimal_profile.model_dump(),
                "files": [
                    FileSpecSchema(
                        source="nonexistent.txt",
                        destination="/etc/test.txt",
                    )
                ],
            }
        )

        staging_dir = tmp_path / "staging"
        with pytest.raises(OverlayStagingError) as exc_info:
            stage_overlay(staging_dir, profile, tmp_path)

        assert "source_not_found" in exc_info.value.code


class TestComputeTreeHash:
    """Tests for compute_tree_hash function."""

    def test_empty_directory(self, tmp_path):
        """Should return consistent hash for empty directory."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        hash1 = compute_tree_hash(empty_dir)
        hash2 = compute_tree_hash(empty_dir)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex digest

    def test_nonexistent_directory(self, tmp_path):
        """Should return empty hash for nonexistent directory."""
        nonexistent = tmp_path / "nonexistent"
        hash1 = compute_tree_hash(nonexistent)
        # Should return empty SHA-256
        import hashlib

        assert hash1 == hashlib.sha256().hexdigest()

    def test_deterministic(self, tmp_path):
        """Should produce same hash for same content."""
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"

        for d in [dir1, dir2]:
            d.mkdir()
            (d / "file1.txt").write_text("content1")
            (d / "file2.txt").write_text("content2")

        assert compute_tree_hash(dir1) == compute_tree_hash(dir2)

    def test_content_affects_hash(self, tmp_path):
        """Should produce different hash for different content."""
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"

        dir1.mkdir()
        dir2.mkdir()

        (dir1 / "file.txt").write_text("content1")
        (dir2 / "file.txt").write_text("content2")

        assert compute_tree_hash(dir1) != compute_tree_hash(dir2)

    def test_filename_affects_hash(self, tmp_path):
        """Should produce different hash for different filenames."""
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"

        dir1.mkdir()
        dir2.mkdir()

        (dir1 / "file1.txt").write_text("content")
        (dir2 / "file2.txt").write_text("content")

        assert compute_tree_hash(dir1) != compute_tree_hash(dir2)

    def test_mode_affects_hash(self, tmp_path):
        """Should produce different hash for different file modes."""
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"

        dir1.mkdir()
        dir2.mkdir()

        f1 = dir1 / "file.txt"
        f2 = dir2 / "file.txt"

        f1.write_text("content")
        f2.write_text("content")

        f1.chmod(0o644)
        f2.chmod(0o755)

        assert compute_tree_hash(dir1) != compute_tree_hash(dir2)

    def test_nested_directories(self, tmp_path):
        """Should hash nested directory structure."""
        root = tmp_path / "root"
        (root / "etc" / "config").mkdir(parents=True)
        (root / "etc" / "banner").write_text("banner")
        (root / "etc" / "config" / "network").write_text("network")

        hash1 = compute_tree_hash(root)
        assert len(hash1) == 64

        # Modifying nested file should change hash
        (root / "etc" / "config" / "network").write_text("modified")
        hash2 = compute_tree_hash(root)

        assert hash1 != hash2


class TestStageAndHashOverlay:
    """Tests for stage_and_hash_overlay convenience function."""

    def test_returns_tuple(self, tmp_path, minimal_profile):
        """Should return tuple of (path, hash)."""
        base_path = tmp_path / "base"
        (base_path / "files").mkdir(parents=True)
        (base_path / "files" / "test.txt").write_text("test")

        profile = ProfileSchema(
            **{
                **minimal_profile.model_dump(),
                "files": [
                    FileSpecSchema(source="files/test.txt", destination="/etc/test.txt")
                ],
            }
        )

        staging_dir = tmp_path / "staging"
        result = stage_and_hash_overlay(staging_dir, profile, base_path)

        assert isinstance(result, tuple)
        assert len(result) == 2

        path, tree_hash = result
        assert path == staging_dir
        assert len(tree_hash) == 64

    def test_consistent_hash(self, tmp_path, minimal_profile):
        """Should produce consistent hash for same content."""
        base_path = tmp_path / "base"
        (base_path / "files").mkdir(parents=True)
        (base_path / "files" / "test.txt").write_text("test content")

        profile = ProfileSchema(
            **{
                **minimal_profile.model_dump(),
                "files": [
                    FileSpecSchema(source="files/test.txt", destination="/etc/test.txt")
                ],
            }
        )

        staging1 = tmp_path / "staging1"
        staging2 = tmp_path / "staging2"

        _, hash1 = stage_and_hash_overlay(staging1, profile, base_path)
        _, hash2 = stage_and_hash_overlay(staging2, profile, base_path)

        assert hash1 == hash2
