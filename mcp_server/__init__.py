"""MCP server exposing OpenWrt Image Generator tools.

This module implements the Model Context Protocol (MCP) server that
exposes the core openwrt_imagegen functionality to AI tools and
external systems.

Per docs/FRONTENDS.md, MCP tools:
- Are idempotent where applicable
- Return structured errors with codes
- Map directly to core services
"""

from mcp_server.server import mcp

__all__ = ["mcp"]
