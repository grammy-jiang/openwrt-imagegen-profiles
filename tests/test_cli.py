"""Smoke tests for the CLI.

These tests verify basic CLI functionality without requiring
network access, database, or external tools.
"""

import subprocess
import sys

from typer.testing import CliRunner

from openwrt_imagegen import __version__
from openwrt_imagegen.cli import app

runner = CliRunner()


class TestCLIHelp:
    """Test CLI help and version commands."""

    def test_help_returns_zero(self) -> None:
        """CLI --help should return exit code 0."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "OpenWrt Image Generator" in result.stdout

    def test_version_flag(self) -> None:
        """CLI --version should print version and exit 0."""
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert __version__ in result.stdout

    def test_short_version_flag(self) -> None:
        """CLI -V should print version and exit 0."""
        result = runner.invoke(app, ["-V"])
        assert result.exit_code == 0
        assert __version__ in result.stdout

    def test_no_args_shows_help(self) -> None:
        """CLI with no args should show help."""
        result = runner.invoke(app, [])
        # Typer with no_args_is_help=True returns exit code 0
        # and shows help text
        assert "Usage:" in result.stdout


class TestCLIConfig:
    """Test CLI config command."""

    def test_config_command(self) -> None:
        """CLI config should show configuration."""
        result = runner.invoke(app, ["config"])
        assert result.exit_code == 0
        assert "Cache directory" in result.stdout

    def test_config_command_shows_all_settings(self) -> None:
        """CLI config should show all configuration fields."""
        result = runner.invoke(app, ["config"])
        assert result.exit_code == 0
        # Check all sections are present
        assert "Paths:" in result.stdout
        assert "Operational:" in result.stdout
        assert "Concurrency:" in result.stdout
        assert "Timeouts (seconds):" in result.stdout
        # Check all fields are displayed
        assert "Cache directory" in result.stdout
        assert "Artifacts directory" in result.stdout
        assert "Database URL" in result.stdout
        assert "Temp directory" in result.stdout
        assert "Offline mode" in result.stdout
        assert "Log level" in result.stdout
        assert "Verification mode" in result.stdout
        assert "Max downloads" in result.stdout
        assert "Max builds" in result.stdout
        assert "Download timeout" in result.stdout
        assert "Build timeout" in result.stdout
        assert "Flash timeout" in result.stdout

    def test_config_json(self) -> None:
        """CLI config --json should output JSON."""
        result = runner.invoke(app, ["config", "--json"])
        assert result.exit_code == 0
        assert "{" in result.stdout
        assert "cache_dir" in result.stdout

    def test_config_json_contains_all_fields(self) -> None:
        """CLI config --json should contain all config fields."""
        import json

        result = runner.invoke(app, ["config", "--json"])
        assert result.exit_code == 0
        config_data = json.loads(result.stdout)
        # Verify all expected keys are present
        expected_keys = [
            "cache_dir",
            "artifacts_dir",
            "db_url",
            "tmp_dir",
            "offline",
            "log_level",
            "max_concurrent_downloads",
            "max_concurrent_builds",
            "verification_mode",
            "download_timeout",
            "build_timeout",
            "flash_timeout",
        ]
        for key in expected_keys:
            assert key in config_data, f"Missing key: {key}"


class TestCLISubcommands:
    """Test that subcommand groups exist."""

    def test_profiles_help(self) -> None:
        """CLI profiles --help should work."""
        result = runner.invoke(app, ["profiles", "--help"])
        assert result.exit_code == 0
        assert "profiles" in result.stdout.lower()

    def test_builders_help(self) -> None:
        """CLI builders --help should work."""
        result = runner.invoke(app, ["builders", "--help"])
        assert result.exit_code == 0
        assert "builders" in result.stdout.lower() or "builder" in result.stdout.lower()

    def test_build_help(self) -> None:
        """CLI build --help should work."""
        result = runner.invoke(app, ["build", "--help"])
        assert result.exit_code == 0
        assert "build" in result.stdout.lower()

    def test_artifacts_help(self) -> None:
        """CLI artifacts --help should work."""
        result = runner.invoke(app, ["artifacts", "--help"])
        assert result.exit_code == 0
        assert "artifact" in result.stdout.lower()

    def test_flash_help(self) -> None:
        """CLI flash --help should work."""
        result = runner.invoke(app, ["flash", "--help"])
        assert result.exit_code == 0
        assert "flash" in result.stdout.lower()


class TestModuleEntryPoint:
    """Test python -m openwrt_imagegen entry point."""

    def test_module_help(self) -> None:
        """python -m openwrt_imagegen --help should work."""
        result = subprocess.run(
            [sys.executable, "-m", "openwrt_imagegen", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "OpenWrt Image Generator" in result.stdout

    def test_module_version(self) -> None:
        """python -m openwrt_imagegen --version should work."""
        result = subprocess.run(
            [sys.executable, "-m", "openwrt_imagegen", "--version"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert __version__ in result.stdout
