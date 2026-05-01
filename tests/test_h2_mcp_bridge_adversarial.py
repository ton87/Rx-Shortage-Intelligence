"""
Adversarial tests for src/mcp_bridge.py — T-004.

Tests edge cases, failure modes, and boundary conditions.
"""

import asyncio
import inspect
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.mcp_bridge import MCPBridge, _server_for_tool, _smoke, CONFIG


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_tool(name, description="A tool", schema=None):
    t = MagicMock()
    t.name = name
    t.description = description
    t.inputSchema = schema or {"type": "object", "properties": {}}
    return t


def _make_mock_client(tools, call_result=None):
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.list_tools = AsyncMock(return_value=tools)
    client.call_tool = AsyncMock(return_value=call_result)
    return client


def _make_text_result(text: str):
    content_item = MagicMock()
    content_item.text = text
    result = MagicMock()
    result.content = [content_item]
    result.structured_content = None
    return result


def _make_structured_result(data: dict):
    result = MagicMock()
    result.content = []
    result.structured_content = {"result": data}
    return result


def _make_empty_result():
    result = MagicMock()
    result.content = []
    result.structured_content = None
    return result


# ---------------------------------------------------------------------------
# Duration logging
# ---------------------------------------------------------------------------

class TestDurationLogging:

    @pytest.mark.asyncio
    async def test_call_tool_logs_duration_ms_as_int(self):
        mock_client = _make_mock_client(
            [_make_mock_tool("fda_shortage_t")],
            call_result=_make_text_result("ok")
        )
        with patch("src.mcp_bridge.Client", return_value=mock_client):
            async with MCPBridge() as bridge:
                await bridge.call_tool("fda_shortage_t", {})
                entry = bridge.tool_calls[0]
        assert isinstance(entry["duration_ms"], int)


# ---------------------------------------------------------------------------
# Empty args dict
# ---------------------------------------------------------------------------

class TestEmptyArgs:

    @pytest.mark.asyncio
    async def test_call_tool_with_empty_args_dict(self):
        """call_tool({}) must work without error."""
        mock_client = _make_mock_client(
            [_make_mock_tool("fda_shortage_t")],
            call_result=_make_text_result("ok")
        )
        with patch("src.mcp_bridge.Client", return_value=mock_client):
            async with MCPBridge() as bridge:
                result = await bridge.call_tool("fda_shortage_t", {})
        assert result == "ok"
        mock_client.call_tool.assert_called_once_with("fda_shortage_t", {})


# ---------------------------------------------------------------------------
# _server_for_tool
# ---------------------------------------------------------------------------

class TestServerForTool:

    def test_server_for_tool_unknown_prefix_returns_unknown(self):
        assert _server_for_tool("completely_unknown_xyz") == "unknown"

    def test_call_tool_server_name_parsed_from_namespace(self):
        """fda_shortage_get_current_shortages -> server=fda_shortage."""
        assert _server_for_tool("fda_shortage_get_current_shortages") == "fda_shortage"


# ---------------------------------------------------------------------------
# Empty description
# ---------------------------------------------------------------------------

class TestEmptyDescription:

    @pytest.mark.asyncio
    async def test_list_tools_empty_description_handled(self):
        """description: '' not None."""
        tools = [_make_mock_tool("fda_shortage_t", description="")]
        mock_client = _make_mock_client(tools)
        with patch("src.mcp_bridge.Client", return_value=mock_client):
            async with MCPBridge() as bridge:
                result = bridge.list_tools()
        assert result[0]["description"] == ""


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

class TestInitialState:

    def test_tool_calls_list_starts_empty(self):
        bridge = MCPBridge()
        assert bridge.tool_calls == []


# ---------------------------------------------------------------------------
# result_preview truncation
# ---------------------------------------------------------------------------

class TestResultPreviewTruncation:

    @pytest.mark.asyncio
    async def test_large_result_preview_capped_at_200_chars(self):
        long_text = "z" * 500
        mock_client = _make_mock_client(
            [_make_mock_tool("fda_shortage_t")],
            call_result=_make_text_result(long_text)
        )
        with patch("src.mcp_bridge.Client", return_value=mock_client):
            async with MCPBridge() as bridge:
                await bridge.call_tool("fda_shortage_t", {})
                entry = bridge.tool_calls[0]
        assert len(entry["result_preview"]) == 200


# ---------------------------------------------------------------------------
# structured_content extraction
# ---------------------------------------------------------------------------

class TestStructuredContent:

    @pytest.mark.asyncio
    async def test_structured_content_result_key_extracted(self):
        """When structured_content has 'result' key, that value is serialized."""
        mock_client = _make_mock_client(
            [_make_mock_tool("fda_shortage_t")],
            call_result=_make_structured_result({"rxcui": "12345"})
        )
        with patch("src.mcp_bridge.Client", return_value=mock_client):
            async with MCPBridge() as bridge:
                text = await bridge.call_tool("fda_shortage_t", {})
        assert json.loads(text) == {"rxcui": "12345"}

    @pytest.mark.asyncio
    async def test_structured_content_without_result_key_uses_full_dict(self):
        """When structured_content has no 'result' key, serialize the whole dict."""
        no_result_key = MagicMock()
        no_result_key.content = []
        no_result_key.structured_content = {"data": "value"}  # no "result" key

        mock_client = _make_mock_client(
            [_make_mock_tool("fda_shortage_t")],
            call_result=no_result_key
        )
        with patch("src.mcp_bridge.Client", return_value=mock_client):
            async with MCPBridge() as bridge:
                text = await bridge.call_tool("fda_shortage_t", {})
        assert json.loads(text) == {"data": "value"}


# ---------------------------------------------------------------------------
# Collision detection
# ---------------------------------------------------------------------------

class TestCollisionCheck:

    @pytest.mark.asyncio
    async def test_collision_check_with_two_tools_same_name(self):
        """RuntimeError if two tools share a name."""
        tools = [
            _make_mock_tool("dup_name"),
            _make_mock_tool("unique_name"),
            _make_mock_tool("dup_name"),
        ]
        mock_client = _make_mock_client(tools)
        with patch("src.mcp_bridge.Client", return_value=mock_client):
            with pytest.raises(RuntimeError, match="Tool name collision"):
                async with MCPBridge():
                    pass


# ---------------------------------------------------------------------------
# Cleanup on list_tools exception
# ---------------------------------------------------------------------------

class TestCleanupOnException:

    @pytest.mark.asyncio
    async def test_aenter_cleans_up_client_on_list_tools_exception(self):
        """If list_tools() raises, __aexit__ must still be called on the client."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.list_tools = AsyncMock(side_effect=ConnectionError("server died"))

        with patch("src.mcp_bridge.Client", return_value=mock_client):
            with pytest.raises(ConnectionError):
                async with MCPBridge():
                    pass

        mock_client.__aexit__.assert_called()


# ---------------------------------------------------------------------------
# _smoke is async
# ---------------------------------------------------------------------------

class TestSmokeFunction:

    def test_smoke_function_exists_and_is_async(self):
        """_smoke is a coroutine function."""
        assert asyncio.iscoroutinefunction(_smoke)
