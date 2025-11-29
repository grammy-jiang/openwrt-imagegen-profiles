"""Error definitions for MCP tools.

This module defines structured error types with stable codes
that can be surfaced to MCP clients. Error codes align with
docs/OPERATIONS.md taxonomy.
"""

from dataclasses import dataclass
from typing import Any

# Error code constants aligned with OPERATIONS.md
VALIDATION_ERROR = "validation"
BUILD_ERROR = "build_failed"
CACHE_CONFLICT_ERROR = "cache_conflict"
FLASH_ERROR = "flash_error"
FLASH_HASH_MISMATCH = "flash_hash_mismatch"
DOWNLOAD_ERROR = "download_error"
PERMISSION_ERROR = "permission_error"
PRECONDITION_ERROR = "precondition_error"
IMAGEBUILDER_ERROR = "imagebuilder_error"
PROFILE_NOT_FOUND = "profile_not_found"
BUILD_NOT_FOUND = "build_not_found"
ARTIFACT_NOT_FOUND = "artifact_not_found"
DEVICE_ERROR = "device_error"
INTERNAL_ERROR = "internal_error"


@dataclass
class MCPError:
    """Structured error response for MCP tools.

    Attributes:
        code: Stable error code for programmatic handling.
        message: Human-readable error message.
        details: Optional additional error details.
        log_path: Optional path to log file with more information.
    """

    code: str
    message: str
    details: dict[str, Any] | None = None
    log_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
        }
        if self.details is not None:
            result["details"] = self.details
        if self.log_path is not None:
            result["log_path"] = self.log_path
        return result


def make_error(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    log_path: str | None = None,
) -> MCPError:
    """Create an MCPError instance.

    Args:
        code: Stable error code.
        message: Human-readable message.
        details: Optional additional details.
        log_path: Optional log file path.

    Returns:
        MCPError instance.
    """
    return MCPError(code=code, message=message, details=details, log_path=log_path)


def validation_error(message: str, details: dict[str, Any] | None = None) -> MCPError:
    """Create a validation error."""
    return make_error(VALIDATION_ERROR, message, details)


def profile_not_found(profile_id: str) -> MCPError:
    """Create a profile not found error."""
    return make_error(
        PROFILE_NOT_FOUND,
        f"Profile not found: {profile_id}",
        details={"profile_id": profile_id},
    )


def build_not_found(build_id: int) -> MCPError:
    """Create a build not found error."""
    return make_error(
        BUILD_NOT_FOUND,
        f"Build not found: {build_id}",
        details={"build_id": build_id},
    )


def artifact_not_found(artifact_id: int) -> MCPError:
    """Create an artifact not found error."""
    return make_error(
        ARTIFACT_NOT_FOUND,
        f"Artifact not found: {artifact_id}",
        details={"artifact_id": artifact_id},
    )


def build_error(
    message: str, log_path: str | None = None, details: dict[str, Any] | None = None
) -> MCPError:
    """Create a build error."""
    return make_error(BUILD_ERROR, message, details, log_path)


def flash_error(
    message: str,
    error_code: str | None = None,
    details: dict[str, Any] | None = None,
) -> MCPError:
    """Create a flash error."""
    code = error_code if error_code else FLASH_ERROR
    return make_error(code, message, details)


def device_error(message: str, device_path: str) -> MCPError:
    """Create a device validation error."""
    return make_error(
        DEVICE_ERROR,
        message,
        details={"device_path": device_path},
    )


__all__ = [
    "ARTIFACT_NOT_FOUND",
    "BUILD_ERROR",
    "BUILD_NOT_FOUND",
    "CACHE_CONFLICT_ERROR",
    "DEVICE_ERROR",
    "DOWNLOAD_ERROR",
    "FLASH_ERROR",
    "FLASH_HASH_MISMATCH",
    "IMAGEBUILDER_ERROR",
    "INTERNAL_ERROR",
    "MCPError",
    "PERMISSION_ERROR",
    "PRECONDITION_ERROR",
    "PROFILE_NOT_FOUND",
    "VALIDATION_ERROR",
    "artifact_not_found",
    "build_error",
    "build_not_found",
    "device_error",
    "flash_error",
    "make_error",
    "profile_not_found",
    "validation_error",
]
