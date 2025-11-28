"""Build runner for executing Image Builder commands.

This module handles:
- Composing Image Builder `make image` commands from profiles
- Executing builds with subprocess
- Capturing stdout/stderr to log files
- Enforcing build timeouts

See docs/BUILD_PIPELINE.md section 7 for design details.
"""

from __future__ import annotations

import logging
import os
import shlex
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from openwrt_imagegen.profiles.schema import ProfileSchema

logger = logging.getLogger(__name__)


class BuildExecutionError(Exception):
    """Raised when build execution fails."""

    def __init__(
        self,
        message: str,
        exit_code: int | None = None,
        code: str = "build_error",
    ) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.code = code


@dataclass
class BuildResult:
    """Result of a build execution.

    Attributes:
        success: Whether the build succeeded.
        exit_code: Process exit code.
        bin_dir: Directory containing output images.
        log_path: Path to the build log file.
        started_at: Build start time.
        finished_at: Build finish time.
        command: The command that was executed.
        error_message: Error message if build failed.
    """

    success: bool
    exit_code: int
    bin_dir: Path
    log_path: Path
    started_at: datetime
    finished_at: datetime
    command: str
    error_message: str | None = None


def compose_packages_arg(
    packages: list[str] | None,
    packages_remove: list[str] | None,
    extra_packages: list[str] | None = None,
) -> str:
    """Compose the PACKAGES argument for Image Builder.

    Args:
        packages: Packages to install from profile.
        packages_remove: Packages to remove from profile.
        extra_packages: Additional packages at build time.

    Returns:
        PACKAGES string value.
    """
    parts: list[str] = []

    # Add packages to install
    if packages:
        parts.extend(packages)

    # Add extra packages
    if extra_packages:
        parts.extend(extra_packages)

    # Add removals with '-' prefix
    if packages_remove:
        for pkg in packages_remove:
            # Avoid duplicates
            if pkg in parts:
                parts.remove(pkg)
            if f"-{pkg}" not in parts:
                parts.append(f"-{pkg}")

    return " ".join(parts)


def compose_make_command(
    profile: ProfileSchema,
    bin_dir: Path,
    files_dir: Path | None = None,
    extra_packages: list[str] | None = None,
    extra_image_name: str | None = None,
) -> list[str]:
    """Compose the `make image` command from a profile.

    Args:
        profile: ProfileSchema instance.
        bin_dir: Directory for output images.
        files_dir: Optional path to staged FILES directory.
        extra_packages: Additional packages at build time.
        extra_image_name: Override for EXTRA_IMAGE_NAME.

    Returns:
        Command as list of strings suitable for subprocess.
    """
    cmd = ["make", "image"]

    # Required PROFILE argument
    cmd.append(f"PROFILE={profile.imagebuilder_profile}")

    # PACKAGES argument
    packages_str = compose_packages_arg(
        profile.packages,
        profile.packages_remove,
        extra_packages,
    )
    if packages_str:
        cmd.append(f"PACKAGES={packages_str}")

    # FILES argument (overlay directory)
    if files_dir and files_dir.exists():
        cmd.append(f"FILES={files_dir}")

    # BIN_DIR argument
    cmd.append(f"BIN_DIR={bin_dir}")

    # Optional arguments from profile
    effective_extra_name = extra_image_name or profile.extra_image_name
    if effective_extra_name:
        cmd.append(f"EXTRA_IMAGE_NAME={effective_extra_name}")

    if profile.disabled_services:
        cmd.append(f"DISABLED_SERVICES={' '.join(profile.disabled_services)}")

    if profile.rootfs_partsize is not None:
        cmd.append(f"ROOTFS_PARTSIZE={profile.rootfs_partsize}")

    if profile.add_local_key:
        cmd.append("ADD_LOCAL_KEY=1")

    return cmd


def run_build(
    profile: ProfileSchema,
    imagebuilder_root: Path,
    build_dir: Path,
    files_dir: Path | None = None,
    extra_packages: list[str] | None = None,
    extra_image_name: str | None = None,
    timeout: int | None = None,
    env_override: dict[str, str] | None = None,
) -> BuildResult:
    """Execute an Image Builder build.

    Args:
        profile: ProfileSchema instance.
        imagebuilder_root: Path to extracted Image Builder root.
        build_dir: Directory for build outputs and logs.
        files_dir: Optional path to staged FILES directory.
        extra_packages: Additional packages at build time.
        extra_image_name: Override for EXTRA_IMAGE_NAME.
        timeout: Build timeout in seconds (None = no timeout).
        env_override: Optional environment variable overrides.

    Returns:
        BuildResult with execution details.

    Raises:
        BuildExecutionError: If build execution fails to start.
    """
    # Create directories
    build_dir.mkdir(parents=True, exist_ok=True)
    bin_dir = build_dir / "bin"
    bin_dir.mkdir(exist_ok=True)
    log_path = build_dir / "build.log"

    # Compose command
    cmd = compose_make_command(
        profile=profile,
        bin_dir=bin_dir,
        files_dir=files_dir,
        extra_packages=extra_packages,
        extra_image_name=extra_image_name,
    )

    # Log the command
    cmd_str = shlex.join(cmd)
    logger.info("Executing build: %s", cmd_str)
    logger.info("Working directory: %s", imagebuilder_root)
    logger.info("Output directory: %s", bin_dir)

    started_at = datetime.now(timezone.utc)
    error_message: str | None = None

    try:
        # Run the build with stdout/stderr captured to log file
        with log_path.open("w") as log_file:
            # Write command to log
            log_file.write(f"# Command: {cmd_str}\n")
            log_file.write(f"# Started: {started_at.isoformat()}\n")
            log_file.write(f"# CWD: {imagebuilder_root}\n")
            log_file.write("# " + "=" * 70 + "\n\n")
            log_file.flush()

            # Prepare environment
            env: dict[str, str] | None = None
            if env_override:
                env = dict(os.environ)
                env.update(env_override)

            # Execute
            result = subprocess.run(
                cmd,
                cwd=imagebuilder_root,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                env=env,
                check=False,
            )

            exit_code = result.returncode
            success = exit_code == 0

            if not success:
                error_message = f"Build failed with exit code {exit_code}"
                logger.error("%s. See log: %s", error_message, log_path)

    except subprocess.TimeoutExpired as e:
        exit_code = -1
        success = False
        error_message = f"Build timed out after {timeout} seconds"
        logger.error("%s. See log: %s", error_message, log_path)

        # Append timeout info to log
        with log_path.open("a") as log_file:
            log_file.write(f"\n# TIMEOUT after {timeout} seconds\n")

        raise BuildExecutionError(
            error_message,
            exit_code=exit_code,
            code="build_timeout",
        ) from e

    except OSError as e:
        error_message = f"Failed to execute build: {e}"
        logger.error(error_message)
        raise BuildExecutionError(
            error_message,
            exit_code=None,
            code="execution_error",
        ) from e

    finished_at = datetime.now(timezone.utc)

    # Append completion info to log
    with log_path.open("a") as log_file:
        log_file.write(f"\n# Finished: {finished_at.isoformat()}\n")
        log_file.write(f"# Exit code: {exit_code}\n")
        duration = (finished_at - started_at).total_seconds()
        log_file.write(f"# Duration: {duration:.1f}s\n")

    return BuildResult(
        success=success,
        exit_code=exit_code,
        bin_dir=bin_dir,
        log_path=log_path,
        started_at=started_at,
        finished_at=finished_at,
        command=cmd_str,
        error_message=error_message,
    )


def validate_imagebuilder_root(root_dir: Path) -> bool:
    """Validate that a directory looks like an Image Builder root.

    Args:
        root_dir: Path to validate.

    Returns:
        True if directory appears to be valid Image Builder.
    """
    if not root_dir.exists():
        return False
    if not root_dir.is_dir():
        return False

    # Check for expected files
    makefile = root_dir / "Makefile"
    if not makefile.exists():
        return False

    # Check for expected directories
    expected_dirs = ["target", "packages"]
    return all((root_dir / d).is_dir() for d in expected_dirs)


def get_make_info(imagebuilder_root: Path, timeout: int = 60) -> dict[str, Any]:
    """Get information from Image Builder using `make info`.

    Args:
        imagebuilder_root: Path to Image Builder root.
        timeout: Command timeout in seconds.

    Returns:
        Dictionary with parsed info (profiles, etc.).

    Raises:
        BuildExecutionError: If command fails.
    """
    if not validate_imagebuilder_root(imagebuilder_root):
        raise BuildExecutionError(
            f"Invalid Image Builder root: {imagebuilder_root}",
            code="invalid_imagebuilder",
        )

    try:
        result = subprocess.run(
            ["make", "info"],
            cwd=imagebuilder_root,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        )

        # Parse output (basic parsing, can be enhanced)
        info: dict[str, Any] = {
            "raw_output": result.stdout,
            "profiles": [],
        }

        # Extract profile names (lines starting with profile name followed by :)
        current_profile: str | None = None
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped.endswith(":") and not stripped.startswith(" "):
                current_profile = stripped.rstrip(":")
                if current_profile not in ("Packages", "Default Packages"):
                    info["profiles"].append(current_profile)

        return info

    except subprocess.TimeoutExpired as e:
        raise BuildExecutionError(
            f"make info timed out after {timeout}s",
            exit_code=-1,
            code="timeout",
        ) from e
    except subprocess.CalledProcessError as e:
        raise BuildExecutionError(
            f"make info failed: {e.stderr}",
            exit_code=e.returncode,
            code="make_info_error",
        ) from e
    except OSError as e:
        raise BuildExecutionError(
            f"Failed to run make info: {e}",
            code="execution_error",
        ) from e


__all__ = [
    "BuildExecutionError",
    "BuildResult",
    "compose_make_command",
    "compose_packages_arg",
    "get_make_info",
    "run_build",
    "validate_imagebuilder_root",
]
