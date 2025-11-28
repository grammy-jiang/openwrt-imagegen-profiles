"""Profile import/export functionality.

This module provides helpers for importing profiles from YAML/JSON files
and exporting profiles from the database to file formats.

See docs/PROFILES.md section 5 for import/export behavior.
"""

import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from openwrt_imagegen.profiles.schema import (
    ProfileBulkImportResult,
    ProfileImportResult,
    ProfileSchema,
)


def load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file and return its contents as a dict.

    Args:
        path: Path to the YAML file.

    Returns:
        Parsed YAML content as a dictionary.

    Raises:
        FileNotFoundError: If the file does not exist.
        yaml.YAMLError: If the file is not valid YAML.
    """
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected a YAML mapping, got {type(data).__name__}")
    return data


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON file and return its contents as a dict.

    Args:
        path: Path to the JSON file.

    Returns:
        Parsed JSON content as a dictionary.

    Raises:
        FileNotFoundError: If the file does not exist.
        json.JSONDecodeError: If the file is not valid JSON.
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object, got {type(data).__name__}")
    return data


def parse_profile_data(data: dict[str, Any]) -> ProfileSchema:
    """Parse and validate profile data using the schema.

    Args:
        data: Dictionary containing profile data.

    Returns:
        Validated ProfileSchema instance.

    Raises:
        pydantic.ValidationError: If data does not match schema.
    """
    profile = ProfileSchema.model_validate(data)
    # Additional validation not handled by Pydantic field validators
    profile.validate_snapshot_policy()
    return profile


def load_profile_from_yaml(path: Path) -> ProfileSchema:
    """Load and validate a profile from a YAML file.

    Args:
        path: Path to the YAML file.

    Returns:
        Validated ProfileSchema instance.

    Raises:
        FileNotFoundError: If the file does not exist.
        yaml.YAMLError: If the file is not valid YAML.
        pydantic.ValidationError: If data does not match schema.
        ValueError: If YAML content is not a mapping or validation fails.
    """
    data = load_yaml(path)
    return parse_profile_data(data)


def load_profile_from_json(path: Path) -> ProfileSchema:
    """Load and validate a profile from a JSON file.

    Args:
        path: Path to the JSON file.

    Returns:
        Validated ProfileSchema instance.

    Raises:
        FileNotFoundError: If the file does not exist.
        json.JSONDecodeError: If the file is not valid JSON.
        pydantic.ValidationError: If data does not match schema.
        ValueError: If JSON content is not an object or validation fails.
    """
    data = load_json(path)
    return parse_profile_data(data)


def load_profile(path: Path) -> ProfileSchema:
    """Load and validate a profile from a file (YAML or JSON).

    File format is determined by extension (.yaml, .yml for YAML,
    .json for JSON).

    Args:
        path: Path to the profile file.

    Returns:
        Validated ProfileSchema instance.

    Raises:
        ValueError: If file extension is not supported.
        FileNotFoundError: If the file does not exist.
        pydantic.ValidationError: If data does not match schema.
    """
    suffix = path.suffix.lower()
    if suffix in (".yaml", ".yml"):
        return load_profile_from_yaml(path)
    elif suffix == ".json":
        return load_profile_from_json(path)
    else:
        raise ValueError(
            f"Unsupported file extension '{suffix}'. Use .yaml, .yml, or .json"
        )


def export_profile_to_yaml(profile: ProfileSchema, path: Path) -> None:
    """Export a profile to a YAML file.

    Args:
        profile: ProfileSchema instance to export.
        path: Path where YAML file should be written.
    """
    data = profile.model_dump(exclude_none=True, exclude_unset=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(
            data, f, default_flow_style=False, allow_unicode=True, sort_keys=False
        )


def export_profile_to_json(profile: ProfileSchema, path: Path) -> None:
    """Export a profile to a JSON file.

    Args:
        profile: ProfileSchema instance to export.
        path: Path where JSON file should be written.
    """
    data = profile.model_dump(exclude_none=True, exclude_unset=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def export_profile(profile: ProfileSchema, path: Path) -> None:
    """Export a profile to a file (YAML or JSON).

    File format is determined by extension (.yaml, .yml for YAML,
    .json for JSON).

    Args:
        profile: ProfileSchema instance to export.
        path: Path where file should be written.

    Raises:
        ValueError: If file extension is not supported.
    """
    suffix = path.suffix.lower()
    if suffix in (".yaml", ".yml"):
        export_profile_to_yaml(profile, path)
    elif suffix == ".json":
        export_profile_to_json(profile, path)
    else:
        raise ValueError(
            f"Unsupported file extension '{suffix}'. Use .yaml, .yml, or .json"
        )


def profile_to_yaml_string(profile: ProfileSchema) -> str:
    """Convert a profile to a YAML string.

    Args:
        profile: ProfileSchema instance to convert.

    Returns:
        YAML string representation.
    """
    data = profile.model_dump(exclude_none=True, exclude_unset=True)
    result: str = yaml.dump(
        data, default_flow_style=False, allow_unicode=True, sort_keys=False
    )
    return result


def profile_to_json_string(profile: ProfileSchema) -> str:
    """Convert a profile to a JSON string.

    Args:
        profile: ProfileSchema instance to convert.

    Returns:
        JSON string representation.
    """
    data = profile.model_dump(exclude_none=True, exclude_unset=True)
    return json.dumps(data, indent=2, ensure_ascii=False)


def load_profiles_from_directory(
    directory: Path,
    pattern: str = "*.yaml",
) -> ProfileBulkImportResult:
    """Load and validate multiple profiles from a directory.

    Args:
        directory: Directory to scan for profile files.
        pattern: Glob pattern for files to load (default: *.yaml).

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
        try:
            profile = load_profile(file_path)
            results.append(
                ProfileImportResult(
                    profile_id=profile.profile_id,
                    success=True,
                    created=True,  # Caller determines actual create/update
                )
            )
        except ValidationError as e:
            # Extract meaningful error message from pydantic
            error_msg = str(e)
            results.append(
                ProfileImportResult(
                    profile_id=file_path.stem,  # Use filename as fallback
                    success=False,
                    error=f"Validation error: {error_msg}",
                )
            )
        except (yaml.YAMLError, json.JSONDecodeError) as e:
            results.append(
                ProfileImportResult(
                    profile_id=file_path.stem,
                    success=False,
                    error=f"Parse error: {e}",
                )
            )
        except ValueError as e:
            results.append(
                ProfileImportResult(
                    profile_id=file_path.stem,
                    success=False,
                    error=str(e),
                )
            )

    succeeded = sum(1 for r in results if r.success)
    failed = len(results) - succeeded

    return ProfileBulkImportResult(
        total=len(results),
        succeeded=succeeded,
        failed=failed,
        results=results,
    )


__all__ = [
    "export_profile",
    "export_profile_to_json",
    "export_profile_to_yaml",
    "load_json",
    "load_profile",
    "load_profile_from_json",
    "load_profile_from_yaml",
    "load_profiles_from_directory",
    "load_yaml",
    "parse_profile_data",
    "profile_to_json_string",
    "profile_to_yaml_string",
]
