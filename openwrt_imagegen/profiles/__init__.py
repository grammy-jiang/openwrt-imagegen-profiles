"""Profile management module.

This module handles:
- ORM models for profiles
- Validation and import/export (YAML/JSON/TOML)
- Query APIs (by profile_id, tag, release, target/subtarget)
- Profile CRUD operations
"""

from openwrt_imagegen.profiles.io import (
    export_profile,
    export_profile_to_json,
    export_profile_to_yaml,
    load_profile,
    load_profile_from_json,
    load_profile_from_yaml,
    load_profiles_from_directory,
    profile_to_json_string,
    profile_to_yaml_string,
)
from openwrt_imagegen.profiles.models import Profile
from openwrt_imagegen.profiles.schema import (
    BuildDefaultsSchema,
    FileSpecSchema,
    ProfileBulkImportResult,
    ProfileImportResult,
    ProfileMetaSchema,
    ProfilePoliciesSchema,
    ProfileSchema,
)
from openwrt_imagegen.profiles.service import (
    ProfileExistsError,
    ProfileNotFoundError,
    create_or_update_profile,
    create_profile,
    delete_profile,
    export_profile_to_file,
    export_profiles_to_directory,
    get_profile,
    get_profile_or_none,
    import_profile_from_file,
    import_profiles_from_directory,
    list_profiles,
    profile_to_schema,
    query_profiles,
    schema_to_profile,
    update_profile,
    validate_profile_data,
)

__all__ = [
    # Models
    "Profile",
    # Schema
    "BuildDefaultsSchema",
    "FileSpecSchema",
    "ProfileBulkImportResult",
    "ProfileImportResult",
    "ProfileMetaSchema",
    "ProfilePoliciesSchema",
    "ProfileSchema",
    # IO functions
    "export_profile",
    "export_profile_to_json",
    "export_profile_to_yaml",
    "load_profile",
    "load_profile_from_json",
    "load_profile_from_yaml",
    "load_profiles_from_directory",
    "profile_to_json_string",
    "profile_to_yaml_string",
    # Service functions
    "ProfileExistsError",
    "ProfileNotFoundError",
    "create_or_update_profile",
    "create_profile",
    "delete_profile",
    "export_profile_to_file",
    "export_profiles_to_directory",
    "get_profile",
    "get_profile_or_none",
    "import_profile_from_file",
    "import_profiles_from_directory",
    "list_profiles",
    "profile_to_schema",
    "query_profiles",
    "schema_to_profile",
    "update_profile",
    "validate_profile_data",
]
