"""Build orchestration module.

This module handles:
- Cache key computation
- Overlay staging
- Running Image Builder
- Artifact discovery and manifest generation
- Build records and cache management
"""

from openwrt_imagegen.builds.models import Artifact, BuildRecord

__all__ = ["Artifact", "BuildRecord"]

# Lazy imports for submodules to avoid circular imports
# Access via openwrt_imagegen.builds.cache_key, etc.
