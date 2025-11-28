"""Image Builder management module.

This module handles:
- Discovering official Image Builder URLs for (release, target, subtarget)
- Downloading/verifying archives and extracting to cache
- Managing Image Builder metadata and cache state
"""

from openwrt_imagegen.imagebuilder.models import ImageBuilder

__all__ = ["ImageBuilder"]
