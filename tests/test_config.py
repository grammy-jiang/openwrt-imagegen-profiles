"""Tests for configuration module."""

import json
import os
from pathlib import Path
from unittest.mock import patch

from openwrt_imagegen.config import Settings, get_settings, print_settings_json


class TestSettings:
    """Test Settings class."""

    def test_default_settings(self) -> None:
        """Settings should have sensible defaults."""
        settings = Settings()

        assert (
            settings.cache_dir
            == Path.home() / ".cache" / "openwrt-imagegen" / "builders"
        )
        assert (
            settings.artifacts_dir
            == Path.home() / ".local" / "share" / "openwrt-imagegen" / "artifacts"
        )
        assert "sqlite" in settings.db_url
        assert settings.offline is False
        assert settings.log_level == "INFO"
        assert settings.max_concurrent_downloads >= 1
        assert settings.max_concurrent_builds >= 1

    def test_settings_from_env(self) -> None:
        """Settings should be loadable from environment variables."""
        with patch.dict(
            os.environ,
            {
                "OWRT_IMG_OFFLINE": "true",
                "OWRT_IMG_LOG_LEVEL": "DEBUG",
                "OWRT_IMG_MAX_CONCURRENT_BUILDS": "4",
            },
        ):
            settings = Settings()
            assert settings.offline is True
            assert settings.log_level == "DEBUG"
            assert settings.max_concurrent_builds == 4

    def test_settings_cache_dir_from_env(self) -> None:
        """Cache dir should be configurable via env."""
        with patch.dict(
            os.environ,
            {
                "OWRT_IMG_CACHE_DIR": "/tmp/test-cache",
            },
        ):
            settings = Settings()
            assert settings.cache_dir == Path("/tmp/test-cache")


class TestGetSettings:
    """Test get_settings function."""

    def test_get_settings_returns_settings(self) -> None:
        """get_settings should return a Settings instance."""
        settings = get_settings()
        assert isinstance(settings, Settings)


class TestPrintSettingsJson:
    """Test print_settings_json function."""

    def test_print_settings_json(self) -> None:
        """print_settings_json should return valid JSON."""
        settings = Settings()
        json_str = print_settings_json(settings)

        # Should be valid JSON
        parsed = json.loads(json_str)

        # Should contain expected keys
        assert "cache_dir" in parsed
        assert "artifacts_dir" in parsed
        assert "db_url" in parsed
        assert "offline" in parsed

    def test_print_settings_json_default(self) -> None:
        """print_settings_json without args should use default settings."""
        json_str = print_settings_json()
        parsed = json.loads(json_str)
        assert "cache_dir" in parsed
