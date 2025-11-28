"""Profile management module.

This module handles:
- ORM models for profiles
- Validation and import/export (YAML/JSON/TOML)
- Query APIs (by profile_id, tag, release, target/subtarget)
- Profile CRUD operations
"""

from openwrt_imagegen.profiles.models import Profile

__all__ = ["Profile"]
