"""Profile service for CRUD and query operations.

This module provides the high-level API for profile management,
including CRUD operations, querying, and bulk import/export with
database persistence.

See docs/ARCHITECTURE.md and docs/PROFILES.md for design context.
"""

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from openwrt_imagegen.profiles.io import (
    export_profile_to_json,
    export_profile_to_yaml,
    load_profile,
    parse_profile_data,
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

if TYPE_CHECKING:
    from sqlalchemy.engine.result import ScalarResult


class ProfileNotFoundError(Exception):
    """Raised when a profile is not found."""

    def __init__(self, profile_id: str) -> None:
        self.profile_id = profile_id
        super().__init__(f"Profile not found: {profile_id}")


class ProfileExistsError(Exception):
    """Raised when attempting to create a profile that already exists."""

    def __init__(self, profile_id: str) -> None:
        self.profile_id = profile_id
        super().__init__(f"Profile already exists: {profile_id}")


def profile_to_schema(profile: Profile, include_meta: bool = False) -> ProfileSchema:
    """Convert a Profile ORM model to a ProfileSchema.

    Args:
        profile: Profile ORM instance.
        include_meta: Whether to include metadata section.

    Returns:
        ProfileSchema instance.
    """
    # Convert files from JSON to FileSpecSchema list
    files: list[FileSpecSchema] | None = None
    if profile.files:
        files = [FileSpecSchema.model_validate(f) for f in profile.files]

    # Convert policies
    policies: ProfilePoliciesSchema | None = None
    if profile.policies:
        policies = ProfilePoliciesSchema.model_validate(profile.policies)

    # Convert build_defaults
    build_defaults: BuildDefaultsSchema | None = None
    if profile.build_defaults:
        build_defaults = BuildDefaultsSchema.model_validate(profile.build_defaults)

    # Convert meta if requested
    meta: ProfileMetaSchema | None = None
    if include_meta:
        meta = ProfileMetaSchema(
            created_at=profile.created_at.isoformat() if profile.created_at else None,
            updated_at=profile.updated_at.isoformat() if profile.updated_at else None,
            created_by=profile.created_by,
        )

    return ProfileSchema(
        profile_id=profile.profile_id,
        name=profile.name,
        description=profile.description,
        device_id=profile.device_id,
        tags=profile.tags,
        openwrt_release=profile.openwrt_release,
        target=profile.target,
        subtarget=profile.subtarget,
        imagebuilder_profile=profile.imagebuilder_profile,
        packages=profile.packages,
        packages_remove=profile.packages_remove,
        files=files,
        overlay_dir=profile.overlay_dir,
        policies=policies,
        build_defaults=build_defaults,
        bin_dir=profile.bin_dir,
        extra_image_name=profile.extra_image_name,
        disabled_services=profile.disabled_services,
        rootfs_partsize=profile.rootfs_partsize,
        add_local_key=profile.add_local_key,
        created_by=profile.created_by,
        notes=profile.notes,
        meta=meta,
    )


def schema_to_profile(schema: ProfileSchema) -> Profile:
    """Convert a ProfileSchema to a Profile ORM model.

    Args:
        schema: ProfileSchema instance.

    Returns:
        Profile ORM instance (not yet added to session).
    """
    # Convert files to dict format for JSON storage
    files: list[dict[str, str]] | None = None
    if schema.files:
        files = [f.model_dump(exclude_none=True) for f in schema.files]

    # Convert policies to dict for JSON storage
    policies: dict[str, Any] | None = None
    if schema.policies:
        policies = schema.policies.model_dump(exclude_none=True)

    # Convert build_defaults to dict for JSON storage
    build_defaults: dict[str, Any] | None = None
    if schema.build_defaults:
        build_defaults = schema.build_defaults.model_dump(exclude_none=True)

    return Profile(
        profile_id=schema.profile_id,
        name=schema.name,
        description=schema.description,
        device_id=schema.device_id,
        tags=schema.tags,
        openwrt_release=schema.openwrt_release,
        target=schema.target,
        subtarget=schema.subtarget,
        imagebuilder_profile=schema.imagebuilder_profile,
        packages=schema.packages,
        packages_remove=schema.packages_remove,
        files=files,
        overlay_dir=schema.overlay_dir,
        policies=policies,
        build_defaults=build_defaults,
        bin_dir=schema.bin_dir,
        extra_image_name=schema.extra_image_name,
        disabled_services=schema.disabled_services,
        rootfs_partsize=schema.rootfs_partsize,
        add_local_key=schema.add_local_key,
        created_by=schema.created_by,
        notes=schema.notes,
    )


def update_profile_from_schema(profile: Profile, schema: ProfileSchema) -> None:
    """Update a Profile ORM model from a ProfileSchema.

    Args:
        profile: Profile ORM instance to update.
        schema: ProfileSchema with new values.
    """
    # Convert files
    files: list[dict[str, str]] | None = None
    if schema.files:
        files = [f.model_dump(exclude_none=True) for f in schema.files]

    # Convert policies
    policies: dict[str, Any] | None = None
    if schema.policies:
        policies = schema.policies.model_dump(exclude_none=True)

    # Convert build_defaults
    build_defaults: dict[str, Any] | None = None
    if schema.build_defaults:
        build_defaults = schema.build_defaults.model_dump(exclude_none=True)

    # Update fields (profile_id is immutable)
    profile.name = schema.name
    profile.description = schema.description
    profile.device_id = schema.device_id
    profile.tags = schema.tags
    profile.openwrt_release = schema.openwrt_release
    profile.target = schema.target
    profile.subtarget = schema.subtarget
    profile.imagebuilder_profile = schema.imagebuilder_profile
    profile.packages = schema.packages
    profile.packages_remove = schema.packages_remove
    profile.files = files
    profile.overlay_dir = schema.overlay_dir
    profile.policies = policies
    profile.build_defaults = build_defaults
    profile.bin_dir = schema.bin_dir
    profile.extra_image_name = schema.extra_image_name
    profile.disabled_services = schema.disabled_services
    profile.rootfs_partsize = schema.rootfs_partsize
    profile.add_local_key = schema.add_local_key
    profile.notes = schema.notes
    # created_by is not updated on existing profiles
    profile.updated_at = datetime.now()


# CRUD Operations


def get_profile(session: Session, profile_id: str) -> Profile:
    """Get a profile by its profile_id.

    Args:
        session: SQLAlchemy session.
        profile_id: The unique profile identifier.

    Returns:
        Profile ORM instance.

    Raises:
        ProfileNotFoundError: If profile does not exist.
    """
    stmt = select(Profile).where(Profile.profile_id == profile_id)
    profile = session.execute(stmt).scalar_one_or_none()
    if profile is None:
        raise ProfileNotFoundError(profile_id)
    return profile


def get_profile_or_none(session: Session, profile_id: str) -> Profile | None:
    """Get a profile by its profile_id, or None if not found.

    Args:
        session: SQLAlchemy session.
        profile_id: The unique profile identifier.

    Returns:
        Profile ORM instance or None.
    """
    stmt = select(Profile).where(Profile.profile_id == profile_id)
    return session.execute(stmt).scalar_one_or_none()


def create_profile(session: Session, schema: ProfileSchema) -> Profile:
    """Create a new profile from a schema.

    Args:
        session: SQLAlchemy session.
        schema: ProfileSchema with profile data.

    Returns:
        Created Profile ORM instance.

    Raises:
        ProfileExistsError: If profile_id already exists.
    """
    # Check for existing profile
    existing = get_profile_or_none(session, schema.profile_id)
    if existing is not None:
        raise ProfileExistsError(schema.profile_id)

    profile = schema_to_profile(schema)
    session.add(profile)
    session.flush()  # Get ID assigned
    return profile


def update_profile(session: Session, profile_id: str, schema: ProfileSchema) -> Profile:
    """Update an existing profile from a schema.

    Args:
        session: SQLAlchemy session.
        profile_id: Profile ID to update.
        schema: ProfileSchema with new values.

    Returns:
        Updated Profile ORM instance.

    Raises:
        ProfileNotFoundError: If profile does not exist.
        ValueError: If schema.profile_id doesn't match profile_id.
    """
    if schema.profile_id != profile_id:
        raise ValueError(
            f"Schema profile_id '{schema.profile_id}' doesn't match "
            f"update target '{profile_id}'"
        )

    profile = get_profile(session, profile_id)
    update_profile_from_schema(profile, schema)
    session.flush()
    return profile


def delete_profile(session: Session, profile_id: str) -> None:
    """Delete a profile by its profile_id.

    Args:
        session: SQLAlchemy session.
        profile_id: The unique profile identifier.

    Raises:
        ProfileNotFoundError: If profile does not exist.
    """
    profile = get_profile(session, profile_id)
    session.delete(profile)
    session.flush()


def create_or_update_profile(
    session: Session, schema: ProfileSchema
) -> tuple[Profile, bool]:
    """Create a profile or update if it already exists.

    Args:
        session: SQLAlchemy session.
        schema: ProfileSchema with profile data.

    Returns:
        Tuple of (Profile, created) where created is True if new profile
        was created, False if existing profile was updated.
    """
    existing = get_profile_or_none(session, schema.profile_id)
    if existing is None:
        profile = schema_to_profile(schema)
        session.add(profile)
        session.flush()
        return profile, True
    else:
        update_profile_from_schema(existing, schema)
        session.flush()
        return existing, False


# Query Operations


def list_profiles(session: Session) -> Sequence[Profile]:
    """List all profiles.

    Args:
        session: SQLAlchemy session.

    Returns:
        Sequence of Profile ORM instances.
    """
    stmt = select(Profile).order_by(Profile.profile_id)
    result: ScalarResult[Profile] = session.execute(stmt).scalars()
    return result.all()


def query_profiles(
    session: Session,
    *,
    device_id: str | None = None,
    openwrt_release: str | None = None,
    target: str | None = None,
    subtarget: str | None = None,
    tags: list[str] | None = None,
) -> Sequence[Profile]:
    """Query profiles with filters.

    Args:
        session: SQLAlchemy session.
        device_id: Filter by device_id.
        openwrt_release: Filter by OpenWrt release.
        target: Filter by target.
        subtarget: Filter by subtarget.
        tags: Filter by tags (profile must have all specified tags).

    Returns:
        Sequence of matching Profile ORM instances.
    """
    stmt = select(Profile)

    if device_id is not None:
        stmt = stmt.where(Profile.device_id == device_id)

    if openwrt_release is not None:
        stmt = stmt.where(Profile.openwrt_release == openwrt_release)

    if target is not None:
        stmt = stmt.where(Profile.target == target)

    if subtarget is not None:
        stmt = stmt.where(Profile.subtarget == subtarget)

    # Tag filtering - profile must have all specified tags
    # Note: JSON array containment varies by database
    # This simple approach works for SQLite with JSON1 extension
    if tags:
        for tag in tags:
            # Use JSON_EACH for SQLite compatibility
            stmt = stmt.where(Profile.tags.contains([tag]))

    stmt = stmt.order_by(Profile.profile_id)
    result: ScalarResult[Profile] = session.execute(stmt).scalars()
    return result.all()


# Import/Export Operations


def import_profile_from_file(
    session: Session,
    path: Path,
    *,
    update_existing: bool = False,
) -> ProfileImportResult:
    """Import a profile from a file.

    Args:
        session: SQLAlchemy session.
        path: Path to the profile file (YAML or JSON).
        update_existing: If True, update existing profiles; if False, fail.

    Returns:
        ProfileImportResult with import status.
    """
    try:
        schema = load_profile(path)

        existing = get_profile_or_none(session, schema.profile_id)
        if existing is not None:
            if not update_existing:
                return ProfileImportResult(
                    profile_id=schema.profile_id,
                    success=False,
                    error=f"Profile already exists: {schema.profile_id}",
                    created=False,
                )
            update_profile_from_schema(existing, schema)
            session.flush()
            return ProfileImportResult(
                profile_id=schema.profile_id,
                success=True,
                created=False,
            )
        else:
            profile = schema_to_profile(schema)
            session.add(profile)
            session.flush()
            return ProfileImportResult(
                profile_id=schema.profile_id,
                success=True,
                created=True,
            )

    except ValidationError as e:
        return ProfileImportResult(
            profile_id=path.stem,
            success=False,
            error=f"Validation error: {e}",
        )
    except ValueError as e:
        return ProfileImportResult(
            profile_id=path.stem,
            success=False,
            error=str(e),
        )
    except Exception as e:
        return ProfileImportResult(
            profile_id=path.stem,
            success=False,
            error=f"Import error: {e}",
        )


def import_profiles_from_directory(
    session: Session,
    directory: Path,
    *,
    pattern: str = "*.yaml",
    update_existing: bool = False,
) -> ProfileBulkImportResult:
    """Import profiles from all matching files in a directory.

    Args:
        session: SQLAlchemy session.
        directory: Directory to scan for profile files.
        pattern: Glob pattern for files (default: *.yaml).
        update_existing: If True, update existing profiles; if False, skip.

    Returns:
        ProfileBulkImportResult with per-file results.

    Raises:
        FileNotFoundError: If directory does not exist.
    """
    if not directory.is_dir():
        raise FileNotFoundError(f"Directory not found: {directory}")

    results: list[ProfileImportResult] = []
    files = sorted(directory.glob(pattern))

    for file_path in files:
        result = import_profile_from_file(
            session, file_path, update_existing=update_existing
        )
        results.append(result)

    succeeded = sum(1 for r in results if r.success)
    failed = len(results) - succeeded

    return ProfileBulkImportResult(
        total=len(results),
        succeeded=succeeded,
        failed=failed,
        results=results,
    )


def export_profile_to_file(
    session: Session,
    profile_id: str,
    path: Path,
    *,
    include_meta: bool = False,
) -> None:
    """Export a profile to a file.

    Args:
        session: SQLAlchemy session.
        profile_id: Profile ID to export.
        path: Output file path (extension determines format).
        include_meta: Whether to include metadata section.

    Raises:
        ProfileNotFoundError: If profile does not exist.
        ValueError: If file extension is not supported.
    """
    profile = get_profile(session, profile_id)
    schema = profile_to_schema(profile, include_meta=include_meta)

    suffix = path.suffix.lower()
    if suffix in (".yaml", ".yml"):
        export_profile_to_yaml(schema, path)
    elif suffix == ".json":
        export_profile_to_json(schema, path)
    else:
        raise ValueError(
            f"Unsupported file extension '{suffix}'. Use .yaml, .yml, or .json"
        )


def export_profiles_to_directory(
    session: Session,
    directory: Path,
    *,
    profile_ids: list[str] | None = None,
    format: str = "yaml",
    include_meta: bool = False,
) -> int:
    """Export profiles to a directory.

    Args:
        session: SQLAlchemy session.
        directory: Output directory.
        profile_ids: List of profile IDs to export, or None for all.
        format: Output format ('yaml' or 'json').
        include_meta: Whether to include metadata section.

    Returns:
        Number of profiles exported.

    Raises:
        ValueError: If format is not supported.
    """
    if format not in ("yaml", "json"):
        raise ValueError(f"Unsupported format '{format}'. Use 'yaml' or 'json'")

    directory.mkdir(parents=True, exist_ok=True)
    # Resolve directory path for security comparison
    resolved_directory = directory.resolve()

    if profile_ids:
        profiles = [get_profile(session, pid) for pid in profile_ids]
    else:
        profiles = list(list_profiles(session))

    ext = ".yaml" if format == "yaml" else ".json"
    count = 0

    for profile in profiles:
        schema = profile_to_schema(profile, include_meta=include_meta)
        # Sanitize profile_id for safe filename:
        # - Replace path separators and control characters
        # - Prevent path traversal with ".."
        import re

        safe_id = profile.profile_id
        # Replace any character that could cause path issues
        safe_id = re.sub(r"[/\\:\*\?\"\<\>\|\x00-\x1f]", "_", safe_id)
        # Prevent path traversal
        safe_id = safe_id.replace("..", "__")
        # Ensure no leading/trailing dots or spaces
        safe_id = safe_id.strip(". ")
        if not safe_id:
            safe_id = f"profile_{profile.id}"
        filename = safe_id + ext
        path = (directory / filename).resolve()
        # Ensure the resolved path is within the intended directory
        if not path.is_relative_to(directory.resolve()):
            raise ValueError(f"Invalid filename would escape directory: {filename}")

        # Security check: ensure the resolved path is within the target directory
        # This prevents path traversal even if sanitization misses something
        resolved_path = path.resolve()
        if not str(resolved_path).startswith(str(resolved_directory)):
            raise ValueError(
                f"Path traversal detected: {filename} would escape target directory"
            )

        if format == "yaml":
            export_profile_to_yaml(schema, path)
        else:
            export_profile_to_json(schema, path)

        count += 1

    return count


def validate_profile_data(data: dict[str, Any]) -> ProfileSchema:
    """Validate profile data without persisting to database.

    Args:
        data: Dictionary containing profile data.

    Returns:
        Validated ProfileSchema instance.

    Raises:
        pydantic.ValidationError: If data does not match schema.
        ValueError: If additional validation fails.
    """
    return parse_profile_data(data)


__all__ = [
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
    "update_profile_from_schema",
    "validate_profile_data",
]
