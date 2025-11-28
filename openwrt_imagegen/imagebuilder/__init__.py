"""Image Builder management module.

This module handles:
- Discovering official Image Builder URLs for (release, target, subtarget)
- Downloading/verifying archives and extracting to cache
- Managing Image Builder metadata and cache state
- Locking for concurrent download prevention
"""

from openwrt_imagegen.imagebuilder.fetch import (
    DownloadError,
    DownloadResult,
    ExtractionError,
    ImageBuilderURLs,
    VerificationError,
    build_imagebuilder_url,
    download_imagebuilder,
)
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

__all__ = [
    # Models
    "ImageBuilder",
    # Fetch module
    "DownloadError",
    "DownloadResult",
    "ExtractionError",
    "ImageBuilderURLs",
    "VerificationError",
    "build_imagebuilder_url",
    "download_imagebuilder",
    # Service module
    "ImageBuilderBrokenError",
    "ImageBuilderNotFoundError",
    "OfflineModeError",
    "builder_lock",
    "ensure_builder",
    "get_builder",
    "get_builder_cache_info",
    "list_builders",
    "prune_builders",
]
