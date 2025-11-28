"""Tests for Image Builder fetch module.

These tests use mocked HTTP responses to test URL discovery,
downloading, checksum verification, and extraction.
"""

import hashlib
import tarfile
from io import BytesIO
from pathlib import Path

import httpx
import pytest
import respx

from openwrt_imagegen.imagebuilder.fetch import (
    OPENWRT_DOWNLOAD_BASE,
    DownloadError,
    DownloadResult,
    ExtractionError,
    ImageBuilderURLs,
    VerificationError,
    build_imagebuilder_url,
    compute_file_sha256,
    download_file,
    download_imagebuilder,
    extract_archive,
    fetch_checksums,
    get_cache_size,
    parse_sha256sums,
    prune_builder,
)


class TestBuildImagebuilderUrl:
    """Tests for build_imagebuilder_url function."""

    def test_release_url(self):
        """Should build correct URL for release builds."""
        urls = build_imagebuilder_url("23.05.3", "ath79", "generic")

        assert isinstance(urls, ImageBuilderURLs)
        assert "releases/23.05.3" in urls.archive_url
        assert "ath79/generic" in urls.archive_url
        assert urls.archive_url.endswith(".tar.xz")
        assert "sha256sums" in urls.sha256sums_url

    def test_snapshot_url(self):
        """Should build correct URL for snapshot builds."""
        urls = build_imagebuilder_url("snapshot", "ramips", "mt7621")

        assert "snapshots" in urls.archive_url
        assert "ramips/mt7621" in urls.archive_url
        assert urls.archive_url.endswith(".tar.zst")

    def test_custom_base_url(self):
        """Should use custom base URL when provided."""
        custom_base = "https://mirror.example.com"
        urls = build_imagebuilder_url("23.05.3", "x86", "64", base_url=custom_base)

        assert urls.archive_url.startswith(custom_base)
        assert urls.sha256sums_url.startswith(custom_base)


class TestParseSha256sums:
    """Tests for parse_sha256sums function."""

    def test_parse_standard_format(self):
        """Should parse standard SHA256SUMS format."""
        content = """abc123def456  openwrt-imagebuilder-23.05.3-ath79-generic.Linux-x86_64.tar.xz
789xyz000111  openwrt-23.05.3-ath79-generic-rootfs.tar.gz
"""
        result = parse_sha256sums(
            content, "openwrt-imagebuilder-23.05.3-ath79-generic.Linux-x86_64.tar.xz"
        )
        assert result == "abc123def456"

    def test_parse_binary_mode_format(self):
        """Should parse binary mode format with asterisk."""
        content = "abc123def456 *openwrt-imagebuilder.tar.xz\n"
        result = parse_sha256sums(content, "openwrt-imagebuilder.tar.xz")
        assert result == "abc123def456"

    def test_file_not_found(self):
        """Should return None if file not in checksums."""
        content = "abc123def456  other-file.tar.xz\n"
        result = parse_sha256sums(content, "missing-file.tar.xz")
        assert result is None

    def test_empty_content(self):
        """Should return None for empty content."""
        result = parse_sha256sums("", "any-file.tar.xz")
        assert result is None

    def test_ignore_comments(self):
        """Should ignore comment lines."""
        content = """# This is a comment
abc123def456  target-file.tar.xz
"""
        result = parse_sha256sums(content, "target-file.tar.xz")
        assert result == "abc123def456"

    def test_lowercase_checksum(self):
        """Should return lowercase checksum."""
        content = "ABC123DEF456  file.tar.xz\n"
        result = parse_sha256sums(content, "file.tar.xz")
        assert result == "abc123def456"


class TestComputeFileSha256:
    """Tests for compute_file_sha256 function."""

    def test_compute_checksum(self, tmp_path):
        """Should compute correct SHA256 checksum."""
        test_file = tmp_path / "test.bin"
        content = b"Hello, World!"
        test_file.write_bytes(content)

        result = compute_file_sha256(test_file)
        expected = hashlib.sha256(content).hexdigest()

        assert result == expected

    def test_large_file_chunked(self, tmp_path):
        """Should correctly compute checksum for files larger than chunk size."""
        test_file = tmp_path / "large.bin"
        # Create content larger than default chunk size
        content = b"A" * (128 * 1024)  # 128 KB
        test_file.write_bytes(content)

        result = compute_file_sha256(test_file, chunk_size=16 * 1024)
        expected = hashlib.sha256(content).hexdigest()

        assert result == expected


class TestDownloadFile:
    """Tests for download_file function."""

    @respx.mock
    def test_successful_download(self, tmp_path):
        """Should download file successfully."""
        content = b"Test file content"
        respx.get("https://example.com/file.bin").mock(
            return_value=httpx.Response(200, content=content)
        )

        dest_path = tmp_path / "downloaded.bin"
        with httpx.Client() as client:
            result = download_file(client, "https://example.com/file.bin", dest_path)

        assert isinstance(result, DownloadResult)
        assert dest_path.exists()
        assert dest_path.read_bytes() == content
        assert result.checksum == hashlib.sha256(content).hexdigest()
        assert result.size_bytes == len(content)

    @respx.mock
    def test_checksum_verification_success(self, tmp_path):
        """Should verify checksum when provided."""
        content = b"Test content"
        expected_checksum = hashlib.sha256(content).hexdigest()
        respx.get("https://example.com/file.bin").mock(
            return_value=httpx.Response(200, content=content)
        )

        dest_path = tmp_path / "verified.bin"
        with httpx.Client() as client:
            result = download_file(
                client,
                "https://example.com/file.bin",
                dest_path,
                expected_checksum=expected_checksum,
            )

        assert result.checksum == expected_checksum
        assert dest_path.exists()

    @respx.mock
    def test_checksum_verification_failure(self, tmp_path):
        """Should raise VerificationError on checksum mismatch."""
        content = b"Test content"
        respx.get("https://example.com/file.bin").mock(
            return_value=httpx.Response(200, content=content)
        )

        dest_path = tmp_path / "bad.bin"
        with httpx.Client() as client, pytest.raises(VerificationError) as exc_info:
            download_file(
                client,
                "https://example.com/file.bin",
                dest_path,
                expected_checksum="wrongchecksum",
            )

        assert "Checksum mismatch" in str(exc_info.value)
        assert not dest_path.exists()  # File should be cleaned up

    @respx.mock
    def test_http_error(self, tmp_path):
        """Should raise DownloadError on HTTP error."""
        respx.get("https://example.com/missing.bin").mock(
            return_value=httpx.Response(404)
        )

        dest_path = tmp_path / "missing.bin"
        with httpx.Client() as client, pytest.raises(DownloadError) as exc_info:
            download_file(client, "https://example.com/missing.bin", dest_path)

        assert exc_info.value.code == "http_error"

    @respx.mock
    def test_timeout_error(self, tmp_path):
        """Should raise DownloadError on timeout."""
        respx.get("https://example.com/slow.bin").mock(
            side_effect=httpx.TimeoutException("Connection timed out")
        )

        dest_path = tmp_path / "slow.bin"
        with httpx.Client() as client, pytest.raises(DownloadError) as exc_info:
            download_file(client, "https://example.com/slow.bin", dest_path)

        assert exc_info.value.code == "timeout"

    @respx.mock
    def test_creates_parent_directories(self, tmp_path):
        """Should create parent directories if they don't exist."""
        content = b"Test"
        respx.get("https://example.com/file.bin").mock(
            return_value=httpx.Response(200, content=content)
        )

        dest_path = tmp_path / "a" / "b" / "c" / "file.bin"
        with httpx.Client() as client:
            download_file(client, "https://example.com/file.bin", dest_path)

        assert dest_path.exists()


class TestFetchChecksums:
    """Tests for fetch_checksums function."""

    @respx.mock
    def test_fetch_success(self):
        """Should fetch checksums successfully."""
        checksums = "abc123  file.tar.xz\n"
        respx.get("https://example.com/sha256sums").mock(
            return_value=httpx.Response(200, text=checksums)
        )

        with httpx.Client() as client:
            result = fetch_checksums(client, "https://example.com/sha256sums")

        assert result == checksums

    @respx.mock
    def test_fetch_http_error(self):
        """Should raise DownloadError on HTTP error."""
        respx.get("https://example.com/sha256sums").mock(
            return_value=httpx.Response(404)
        )

        with httpx.Client() as client, pytest.raises(DownloadError) as exc_info:
            fetch_checksums(client, "https://example.com/sha256sums")

        assert exc_info.value.code == "http_error"


class TestExtractArchive:
    """Tests for extract_archive function."""

    def _create_tar_xz(self, tmp_path: Path, content_dir: str, files: dict) -> Path:
        """Helper to create a .tar.xz archive."""
        import lzma

        archive_path = tmp_path / "test.tar.xz"

        # Create tar in memory
        tar_bytes = BytesIO()
        with tarfile.open(fileobj=tar_bytes, mode="w") as tar:
            for name, content in files.items():
                full_name = f"{content_dir}/{name}"
                info = tarfile.TarInfo(name=full_name)
                data = content.encode() if isinstance(content, str) else content
                info.size = len(data)
                tar.addfile(info, BytesIO(data))

        # Compress with xz
        tar_bytes.seek(0)
        with lzma.open(archive_path, "wb") as xz_file:
            xz_file.write(tar_bytes.read())

        return archive_path

    def test_extract_tar_xz(self, tmp_path):
        """Should extract .tar.xz archive."""
        archive = self._create_tar_xz(
            tmp_path,
            "openwrt-imagebuilder",
            {"Makefile": "# Test Makefile", "README": "Test readme"},
        )

        dest_dir = tmp_path / "extracted"
        root_dir = extract_archive(archive, dest_dir)

        assert root_dir.exists()
        assert (root_dir / "Makefile").exists()
        assert (root_dir / "README").exists()

    def test_extract_removes_archive(self, tmp_path):
        """Should remove archive when remove_archive=True."""
        archive = self._create_tar_xz(
            tmp_path,
            "openwrt-imagebuilder",
            {"file.txt": "content"},
        )

        dest_dir = tmp_path / "extracted"
        extract_archive(archive, dest_dir, remove_archive=True)

        assert not archive.exists()

    def test_extract_keeps_archive(self, tmp_path):
        """Should keep archive when remove_archive=False."""
        archive = self._create_tar_xz(
            tmp_path,
            "openwrt-imagebuilder",
            {"file.txt": "content"},
        )

        dest_dir = tmp_path / "extracted"
        extract_archive(archive, dest_dir, remove_archive=False)

        assert archive.exists()

    def test_extract_unsupported_format(self, tmp_path):
        """Should raise ExtractionError for unsupported format."""
        archive = tmp_path / "test.zip"
        archive.write_bytes(b"not a tar archive")

        dest_dir = tmp_path / "extracted"
        with pytest.raises(ExtractionError) as exc_info:
            extract_archive(archive, dest_dir)

        assert exc_info.value.code == "unsupported_format"

    def test_extract_tar_xz_path_traversal_absolute(self, tmp_path):
        """Should reject .tar.xz archives with absolute paths."""
        import lzma

        archive_path = tmp_path / "malicious.tar.xz"

        # Create tar with absolute path
        tar_bytes = BytesIO()
        with tarfile.open(fileobj=tar_bytes, mode="w") as tar:
            info = tarfile.TarInfo(name="/etc/passwd")
            info.size = 4
            tar.addfile(info, BytesIO(b"test"))

        tar_bytes.seek(0)
        with lzma.open(archive_path, "wb") as xz_file:
            xz_file.write(tar_bytes.read())

        dest_dir = tmp_path / "extracted"
        with pytest.raises(ExtractionError) as exc_info:
            extract_archive(archive_path, dest_dir)

        assert exc_info.value.code == "path_traversal"

    def test_extract_tar_xz_path_traversal_dotdot(self, tmp_path):
        """Should reject .tar.xz archives with .. path components."""
        import lzma

        archive_path = tmp_path / "malicious.tar.xz"

        # Create tar with path traversal
        tar_bytes = BytesIO()
        with tarfile.open(fileobj=tar_bytes, mode="w") as tar:
            info = tarfile.TarInfo(name="../../../etc/passwd")
            info.size = 4
            tar.addfile(info, BytesIO(b"test"))

        tar_bytes.seek(0)
        with lzma.open(archive_path, "wb") as xz_file:
            xz_file.write(tar_bytes.read())

        dest_dir = tmp_path / "extracted"
        with pytest.raises(ExtractionError) as exc_info:
            extract_archive(archive_path, dest_dir)

        assert exc_info.value.code == "path_traversal"

    def test_extract_tar_zst_relative_path(self, tmp_path):
        """Should reject .tar.zst extraction with relative paths."""
        archive_path = tmp_path / "test.tar.zst"
        archive_path.write_bytes(b"fake content")

        # Use a relative path - should fail path validation
        dest_dir = Path("relative/path")
        with pytest.raises(ExtractionError) as exc_info:
            extract_archive(archive_path, dest_dir)

        assert exc_info.value.code == "path_error"


class TestPruneBuilder:
    """Tests for prune_builder function."""

    def test_prune_existing_directory(self, tmp_path):
        """Should remove existing builder directory."""
        builder_dir = tmp_path / "23.05.3" / "ath79" / "generic"
        builder_dir.mkdir(parents=True)
        (builder_dir / "Makefile").write_text("test")

        result = prune_builder(builder_dir)

        assert result is True
        assert not builder_dir.exists()

    def test_prune_nonexistent_directory(self, tmp_path):
        """Should return False for nonexistent directory."""
        builder_dir = tmp_path / "nonexistent"

        result = prune_builder(builder_dir)

        assert result is False


class TestGetCacheSize:
    """Tests for get_cache_size function."""

    def test_empty_cache(self, tmp_path):
        """Should return 0 for empty cache."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()

        size = get_cache_size(cache_dir)
        assert size == 0

    def test_nonexistent_cache(self, tmp_path):
        """Should return 0 for nonexistent cache."""
        cache_dir = tmp_path / "nonexistent"

        size = get_cache_size(cache_dir)
        assert size == 0

    def test_cache_with_files(self, tmp_path):
        """Should calculate correct size."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()

        # Create some files
        (cache_dir / "file1.txt").write_bytes(b"A" * 100)
        subdir = cache_dir / "subdir"
        subdir.mkdir()
        (subdir / "file2.txt").write_bytes(b"B" * 200)

        size = get_cache_size(cache_dir)
        assert size == 300


class TestImageBuilderURLsValidation:
    """Tests for ImageBuilderURLs dataclass validation."""

    def test_valid_urls(self):
        """Should accept valid URLs."""
        urls = ImageBuilderURLs(
            archive_url="https://example.com/archive.tar.xz",
            sha256sums_url="https://example.com/sha256sums",
        )
        assert urls.archive_url == "https://example.com/archive.tar.xz"

    def test_missing_archive_url(self):
        """Should raise ValueError for missing archive_url."""
        with pytest.raises(ValueError) as exc_info:
            ImageBuilderURLs(
                archive_url="",
                sha256sums_url="https://example.com/sha256sums",
            )
        assert "archive_url" in str(exc_info.value)

    def test_missing_sha256sums_url(self):
        """Should raise ValueError for missing sha256sums_url."""
        with pytest.raises(ValueError) as exc_info:
            ImageBuilderURLs(
                archive_url="https://example.com/archive.tar.xz",
                sha256sums_url="",
            )
        assert "sha256sums_url" in str(exc_info.value)


class TestDownloadImagebuilderIntegration:
    """Integration tests for download_imagebuilder function."""

    def _create_mock_archive(
        self, tmp_path: Path, name: str
    ) -> tuple[Path, str, bytes]:
        """Create a mock archive and return path, checksum, and content."""
        import lzma

        # Create a simple tar archive
        tar_bytes = BytesIO()
        with tarfile.open(fileobj=tar_bytes, mode="w") as tar:
            info = tarfile.TarInfo(name=f"{name}/Makefile")
            content = b"# Mock Makefile"
            info.size = len(content)
            tar.addfile(info, BytesIO(content))

        # Compress with xz
        tar_bytes.seek(0)
        xz_content = lzma.compress(tar_bytes.read())

        # Calculate checksum
        checksum = hashlib.sha256(xz_content).hexdigest()

        return tmp_path / f"{name}.tar.xz", checksum, xz_content

    @respx.mock
    def test_download_and_extract(self, tmp_path):
        """Should download, verify, and extract Image Builder."""
        archive_path, checksum, content = self._create_mock_archive(
            tmp_path, "openwrt-imagebuilder-23.05.3-ath79-generic.Linux-x86_64"
        )
        archive_name = "openwrt-imagebuilder-23.05.3-ath79-generic.Linux-x86_64.tar.xz"

        # Mock HTTP responses
        respx.get(
            f"{OPENWRT_DOWNLOAD_BASE}/releases/23.05.3/targets/ath79/generic/{archive_name}"
        ).mock(return_value=httpx.Response(200, content=content))
        respx.get(
            f"{OPENWRT_DOWNLOAD_BASE}/releases/23.05.3/targets/ath79/generic/sha256sums"
        ).mock(return_value=httpx.Response(200, text=f"{checksum}  {archive_name}\n"))

        cache_dir = tmp_path / "cache"

        with httpx.Client() as client:
            root_dir, result_checksum = download_imagebuilder(
                client,
                release="23.05.3",
                target="ath79",
                subtarget="generic",
                cache_dir=cache_dir,
            )

        assert root_dir.exists()
        assert (root_dir / "Makefile").exists()
        assert result_checksum == checksum

    @respx.mock
    def test_download_checksum_mismatch(self, tmp_path):
        """Should fail on checksum mismatch."""
        content = b"some archive content"
        archive_name = "openwrt-imagebuilder-23.05.3-ath79-generic.Linux-x86_64.tar.xz"

        respx.get(
            f"{OPENWRT_DOWNLOAD_BASE}/releases/23.05.3/targets/ath79/generic/{archive_name}"
        ).mock(return_value=httpx.Response(200, content=content))
        respx.get(
            f"{OPENWRT_DOWNLOAD_BASE}/releases/23.05.3/targets/ath79/generic/sha256sums"
        ).mock(
            return_value=httpx.Response(200, text=f"wrongchecksum  {archive_name}\n")
        )

        cache_dir = tmp_path / "cache"

        with httpx.Client() as client, pytest.raises(VerificationError):
            download_imagebuilder(
                client,
                release="23.05.3",
                target="ath79",
                subtarget="generic",
                cache_dir=cache_dir,
            )
