"""FastAPI web application for OpenWrt Image Generator.

This module provides the HTTP API that mirrors the core services,
following the architecture defined in docs/FRONTENDS.md.

All business logic is delegated to core modules in openwrt_imagegen/.
"""

from web.app import app, create_app

__all__ = ["app", "create_app"]
