"""Tool errors must reach the client, redacted: MCP SDK 2 hides unexpected exception text."""

from __future__ import annotations

import asyncio

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from apple_ads_mcp.client import AppleAdsAPIError
from apple_ads_mcp.server import AppleAdsMCPServer


def _server() -> AppleAdsMCPServer:
    mcp = AppleAdsMCPServer("test")

    @mcp.tool()
    def apple_ads_refuses(confirm: str = "") -> dict:
        """Refuses unless confirmed."""
        raise ValueError("Pass confirm='DELETE' to proceed.")

    @mcp.tool()
    def apple_ads_api_fails() -> dict:
        """Fails like the API."""
        raise AppleAdsAPIError(403, {"error": {"code": "FORBIDDEN", "message": "no"}})

    @mcp.tool()
    def apple_ads_leaks() -> dict:
        """Error text containing a token."""
        raise RuntimeError("upstream said Bearer eyJhbGciOiJFUzI1NiJ9.eyJzdWIiOiJ4In0.c2ln")

    @mcp.tool()
    def apple_ads_crashes() -> dict:
        """Crashes with an unexpected error."""
        raise KeyError("internal detail")

    return mcp


@pytest.mark.parametrize(
    ("tool", "message"),
    [
        ("apple_ads_refuses", "Pass confirm='DELETE' to proceed."),
        ("apple_ads_api_fails", "Apple Ads API error 403"),
    ],
)
def test_expected_errors_keep_their_message(tool: str, message: str) -> None:
    with pytest.raises(ToolError, match=message.split(":")[0]):
        asyncio.run(_server().call_tool(tool, {}))


def test_error_messages_are_redacted() -> None:
    with pytest.raises(ToolError) as exc_info:
        asyncio.run(_server().call_tool("apple_ads_leaks", {}))
    assert "eyJ" not in str(exc_info.value)
    assert "[REDACTED]" in str(exc_info.value)


def test_unexpected_errors_stay_hidden() -> None:
    with pytest.raises(Exception) as exc_info:
        asyncio.run(_server().call_tool("apple_ads_crashes", {}))
    assert "internal detail" not in str(exc_info.value)
