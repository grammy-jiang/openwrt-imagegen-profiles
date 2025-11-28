"""Image Builder fetch module.

This module handles:
- URL discovery for official Image Builder archives
- Download with checksum verification
- Extraction to cache directory
- Pruning helpers for cache management
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

# Official OpenWrt download server base URL
OPENWRT_DOWNLOAD_BASE = "https://downloads.openwrt.org"

# Timeout for HEAD requests (seconds)
HEAD_TIMEOUT = 30

# Timeout for downloads (seconds)
DOWNLOAD_TIMEOUT = 3600

# Chunk size for downloads (bytes)
DOWNLOAD_CHUNK_SIZE = 64 * 1024  # 64 KB


class DownloadError(Exception):
    """Raised when Image Builder download fails."""

    def __init__(self, message: str, code: str = "download_error") -> None:
        """Initialize DownloadError.

        Args:
            message: Error description.
            code: Error code for structured error handling.
        """
        super().__init__(message)
        self.code = code


class VerificationError(Exception):
    """Raised when checksum verification fails."""

    def __init__(self, message: str, code: str = "verification_error") -> None:
        """Initialize VerificationError.

        Args:
            message: Error description.
            code: Error code for structured error handling.
        """
        super().__init__(message)
        self.code = code


class ExtractionError(Exception):
    """Raised when archive extraction fails."""

    def __init__(self, message: str, code: str = "extraction_error") -> None:
        """Initialize ExtractionError.

        Args:
            message: Error description.
            code: Error code for structured error handling.
        """
        super().__init__(message)
        self.code = code


@dataclass
class ImageBuilderURLs:
    """URLs for Image Builder archive and related files."""

    archive_url: str
    sha256sums_url: str
    gpg_signature_url: str | None = None

    def __post_init__(self) -> None:
        """Validate URLs after initialization."""
        if not self.archive_url:
            raise ValueError("archive_url must be provided")
        if not self.sha256sums_url:
            raise ValueError("sha256sums_url must be provided")


@dataclass
class DownloadResult:
    """Result of an Image Builder download."""

    archive_path: Path
    checksum: str
    size_bytes: int
    signature_verified: bool = False


def build_imagebuilder_url(
    release: str,
    target: str,
    subtarget: str,
    base_url: str = OPENWRT_DOWNLOAD_BASE,
) -> ImageBuilderURLs:
    """Build URLs for Image Builder archive and checksums.

    Args:
        release: OpenWrt release version (e.g., '23.05.3' or 'snapshot').
        target: Target platform (e.g., 'ath79').
        subtarget: Subtarget (e.g., 'generic').
        base_url: Base URL for OpenWrt downloads.

    Returns:
        ImageBuilderURLs with archive, checksum, and signature URLs.
    """
    if release.lower() == "snapshot":
        # Snapshot builds use a different path structure
        path_prefix = f"{base_url}/snapshots/targets/{target}/{subtarget}"
        archive_name = f"openwrt-imagebuilder-{target}-{subtarget}.Linux-x86_64.tar.zst"
    else:
        # Release builds
        path_prefix = f"{base_url}/releases/{release}/targets/{target}/{subtarget}"
        archive_name = (
            f"openwrt-imagebuilder-{release}-{target}-{subtarget}.Linux-x86_64.tar.xz"
        )

    return ImageBuilderURLs(
        archive_url=f"{path_prefix}/{archive_name}",
        sha256sums_url=f"{path_prefix}/sha256sums",
        gpg_signature_url=f"{path_prefix}/sha256sums.asc",
    )


def parse_sha256sums(content: str, archive_filename: str) -> str | None:
    """Parse SHA256SUMS file to find checksum for a specific file.

    Args:
        content: Content of SHA256SUMS file.
        archive_filename: Filename to look up.

    Returns:
        SHA256 checksum string, or None if not found.
    """
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            continue

        checksum, filename = parts
        # Remove leading '*' if present (binary mode indicator)
        filename = filename.lstrip("*").strip()

        if filename == archive_filename:
            return checksum.lower()

    return None


def compute_file_sha256(file_path: Path, chunk_size: int = DOWNLOAD_CHUNK_SIZE) -> str:
    """Compute SHA256 checksum of a file.

    Args:
        file_path: Path to the file.
        chunk_size: Size of chunks to read.

    Returns:
        SHA256 hex digest.
    """
    sha256 = hashlib.sha256()
    with file_path.open("rb") as f:
        while chunk := f.read(chunk_size):
            sha256.update(chunk)
    return sha256.hexdigest()


def download_file(
    client: httpx.Client,
    url: str,
    dest_path: Path,
    expected_checksum: str | None = None,
    timeout: float = DOWNLOAD_TIMEOUT,
    chunk_size: int = DOWNLOAD_CHUNK_SIZE,
) -> DownloadResult:
    """Download a file with optional checksum verification.

    Args:
        client: HTTPX client instance.
        url: URL to download from.
        dest_path: Destination path for the downloaded file.
        expected_checksum: Expected SHA256 checksum (optional).
        timeout: Download timeout in seconds.
        chunk_size: Size of chunks to download.

    Returns:
        DownloadResult with path, checksum, and size.

    Raises:
        DownloadError: If download fails.
        VerificationError: If checksum verification fails.
    """
    logger.info("Downloading %s to %s", url, dest_path)

    try:
        with client.stream("GET", url, timeout=timeout) as response:
            response.raise_for_status()

            total_bytes = 0
            sha256 = hashlib.sha256()

            dest_path.parent.mkdir(parents=True, exist_ok=True)

            with dest_path.open("wb") as f:
                for chunk in response.iter_bytes(chunk_size):
                    f.write(chunk)
                    sha256.update(chunk)
                    total_bytes += len(chunk)

            computed_checksum = sha256.hexdigest()

            if expected_checksum and computed_checksum != expected_checksum.lower():
                # Remove the corrupted file
                dest_path.unlink(missing_ok=True)
                raise VerificationError(
                    f"Checksum mismatch for {url}: "
                    f"expected {expected_checksum}, got {computed_checksum}"
                )

            logger.info(
                "Downloaded %s (%d bytes, checksum: %s)",
                dest_path.name,
                total_bytes,
                computed_checksum[:16] + "...",
            )

            return DownloadResult(
                archive_path=dest_path,
                checksum=computed_checksum,
                size_bytes=total_bytes,
            )

    except httpx.HTTPStatusError as e:
        raise DownloadError(
            f"HTTP error downloading {url}: {e.response.status_code} {e.response.reason_phrase}",
            code="http_error",
        ) from e
    except httpx.TimeoutException as e:
        raise DownloadError(
            f"Timeout downloading {url}",
            code="timeout",
        ) from e
    except httpx.RequestError as e:
        raise DownloadError(
            f"Network error downloading {url}: {e}",
            code="network_error",
        ) from e


def fetch_checksums(
    client: httpx.Client,
    sha256sums_url: str,
    timeout: float = HEAD_TIMEOUT,
) -> str:
    """Fetch SHA256SUMS file content.

    Args:
        client: HTTPX client instance.
        sha256sums_url: URL to SHA256SUMS file.
        timeout: Request timeout in seconds.

    Returns:
        Content of SHA256SUMS file.

    Raises:
        DownloadError: If fetch fails.
    """
    logger.debug("Fetching checksums from %s", sha256sums_url)

    try:
        response = client.get(sha256sums_url, timeout=timeout)
        response.raise_for_status()
        return response.text

    except httpx.HTTPStatusError as e:
        raise DownloadError(
            f"HTTP error fetching checksums: {e.response.status_code}",
            code="http_error",
        ) from e
    except httpx.TimeoutException as e:
        raise DownloadError(
            f"Timeout fetching checksums from {sha256sums_url}",
            code="timeout",
        ) from e
    except httpx.RequestError as e:
        raise DownloadError(
            f"Network error fetching checksums: {e}",
            code="network_error",
        ) from e


def extract_archive(
    archive_path: Path,
    dest_dir: Path,
    remove_archive: bool = False,
) -> Path:
    """Extract Image Builder archive to destination directory.

    Args:
        archive_path: Path to the archive file.
        dest_dir: Destination directory for extraction.
        remove_archive: Whether to remove the archive after extraction.

    Returns:
        Path to the extracted Image Builder root directory.

    Raises:
        ExtractionError: If extraction fails.
    """
    logger.info("Extracting %s to %s", archive_path.name, dest_dir)

    dest_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Determine archive type from extension
        suffix = archive_path.suffix.lower()
        suffixes = "".join(archive_path.suffixes).lower()

        if suffixes.endswith(".tar.xz") or suffixes.endswith(".tar.zst"):
            # For .tar.zst, we need to use a different approach
            if suffixes.endswith(".tar.zst"):
                # Security: Validate paths before subprocess call
                # archive_path and dest_dir are Path objects from controlled sources
                # (cache_dir from settings, not user input)
                if not archive_path.is_absolute() or not dest_dir.is_absolute():
                    raise ExtractionError(
                        "Archive path and destination must be absolute paths",
                        code="path_error",
                    )

                # Use system tar command for zstd support (not shell=True, list args)
                import subprocess

                result = subprocess.run(
                    ["tar", "-xf", str(archive_path), "-C", str(dest_dir)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode != 0:
                    raise ExtractionError(
                        f"Failed to extract {archive_path}: {result.stderr}",
                        code="tar_error",
                    )
            else:
                # Handle .tar.xz archives
                with tarfile.open(archive_path, "r:xz") as tar:
                    # Get the top-level directory name
                    members = tar.getmembers()
                    if not members:
                        raise ExtractionError(
                            f"Archive {archive_path} is empty",
                            code="empty_archive",
                        )

                    # Extract all members safely
                    for member in members:
                        # Security: prevent path traversal
                        member_path = Path(member.name)
                        if member_path.is_absolute() or ".." in member_path.parts:
                            raise ExtractionError(
                                f"Refusing to extract {member.name}: path traversal detected",
                                code="path_traversal",
                            )

                    tar.extractall(dest_dir, filter="data")

        elif suffix == ".tar":
            with tarfile.open(archive_path, "r:") as tar:
                tar.extractall(dest_dir, filter="data")
        else:
            raise ExtractionError(
                f"Unsupported archive format: {archive_path.suffix}",
                code="unsupported_format",
            )

        # Find the extracted directory (should be the only top-level dir)
        extracted_dirs = [
            d for d in dest_dir.iterdir() if d.is_dir() and d.name.startswith("openwrt")
        ]

        if len(extracted_dirs) == 1:
            root_dir = extracted_dirs[0]
        elif not extracted_dirs:
            # Maybe the extraction created the expected structure directly
            root_dir = dest_dir
        else:
            # Multiple directories - unexpected
            logger.warning(
                "Multiple directories found after extraction: %s",
                [d.name for d in extracted_dirs],
            )
            root_dir = extracted_dirs[0]

        if remove_archive:
            archive_path.unlink()
            logger.debug("Removed archive %s", archive_path)

        logger.info("Extracted Image Builder to %s", root_dir)
        return root_dir

    except tarfile.TarError as e:
        raise ExtractionError(
            f"Failed to extract {archive_path}: {e}",
            code="tar_error",
        ) from e
    except OSError as e:
        raise ExtractionError(
            f"OS error extracting {archive_path}: {e}",
            code="os_error",
        ) from e


def download_imagebuilder(
    client: httpx.Client,
    release: str,
    target: str,
    subtarget: str,
    cache_dir: Path,
    base_url: str = OPENWRT_DOWNLOAD_BASE,
    verify_checksum: bool = True,
    keep_archive: bool = False,
) -> tuple[Path, str]:
    """Download and extract an Image Builder.

    Args:
        client: HTTPX client instance.
        release: OpenWrt release version.
        target: Target platform.
        subtarget: Subtarget.
        cache_dir: Root cache directory.
        base_url: Base URL for downloads.
        verify_checksum: Whether to verify SHA256 checksum.
        keep_archive: Whether to keep the archive after extraction.

    Returns:
        Tuple of (extracted root directory path, checksum).

    Raises:
        DownloadError: If download fails.
        VerificationError: If checksum verification fails.
        ExtractionError: If extraction fails.
    """
    urls = build_imagebuilder_url(release, target, subtarget, base_url)

    # Determine archive filename from URL
    archive_filename = urls.archive_url.rsplit("/", 1)[-1]

    # Build paths
    builder_dir = cache_dir / release / target / subtarget
    builder_dir.mkdir(parents=True, exist_ok=True)

    # Use a temp file for download, then move to final location
    with tempfile.NamedTemporaryFile(
        dir=builder_dir, suffix=".tmp", delete=False
    ) as tmp_file:
        tmp_path = Path(tmp_file.name)

    expected_checksum: str | None = None

    try:
        # Fetch checksums if verification enabled
        if verify_checksum:
            checksums_content = fetch_checksums(client, urls.sha256sums_url)
            expected_checksum = parse_sha256sums(checksums_content, archive_filename)

            if not expected_checksum:
                logger.warning(
                    "Could not find checksum for %s in SHA256SUMS", archive_filename
                )

        # Download the archive
        result = download_file(
            client,
            urls.archive_url,
            tmp_path,
            expected_checksum=expected_checksum,
        )

        # Move to final archive path if keeping
        archive_path = builder_dir / archive_filename
        shutil.move(str(tmp_path), str(archive_path))

        # Extract
        root_dir = extract_archive(
            archive_path,
            builder_dir,
            remove_archive=not keep_archive,
        )

        return root_dir, result.checksum

    except Exception:
        # Clean up temp file on failure
        tmp_path.unlink(missing_ok=True)
        raise


def prune_builder(
    builder_dir: Path,
) -> bool:
    """Remove an Image Builder from the cache.

    Args:
        builder_dir: Path to the Image Builder directory.

    Returns:
        True if successfully removed, False if directory didn't exist.
    """
    if not builder_dir.exists():
        return False

    logger.info("Pruning Image Builder at %s", builder_dir)

    try:
        shutil.rmtree(builder_dir)
        return True
    except OSError as e:
        logger.error("Failed to prune %s: %s", builder_dir, e)
        raise


def get_cache_size(cache_dir: Path) -> int:
    """Calculate total size of Image Builder cache.

    Args:
        cache_dir: Root cache directory.

    Returns:
        Total size in bytes.
    """
    total = 0
    if cache_dir.exists():
        for path in cache_dir.rglob("*"):
            if path.is_file():
                total += path.stat().st_size
    return total


__all__ = [
    "DownloadError",
    "DownloadResult",
    "ExtractionError",
    "ImageBuilderURLs",
    "OPENWRT_DOWNLOAD_BASE",
    "VerificationError",
    "build_imagebuilder_url",
    "compute_file_sha256",
    "download_file",
    "download_imagebuilder",
    "extract_archive",
    "fetch_checksums",
    "get_cache_size",
    "parse_sha256sums",
    "prune_builder",
]
