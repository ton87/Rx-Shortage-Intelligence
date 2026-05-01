"""
Contract tests for src/mcp_bridge.py — T-004.

All tests use unittest.mock to avoid spawning real MCP servers.
"""

import asyncio
import inspect
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.mcp_bridge import MCPBridge, _mcp_to_anthropic, CONFIG


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_tool(name, description="A tool", schema=None):
    """Return a MagicMock that looks like an MCP Tool object."""
    t = MagicMock()
    t.name = name
    t.description = description
    t.inputSchema = schema or {"type": "object", "properties": {}}
    return t


def _make_mock_client(tools, call_result=None):
    """Return an AsyncMock client that returns the given tools list."""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.list_tools = AsyncMock(return_value=tools)
    client.call_tool = AsyncMock(return_value=call_result)
    return client


def _make_text_result(text: str):
    """Return a mock call_tool result with .content[0].text == text."""
    content_item = MagicMock()
    content_item.text = text
    result = MagicMock()
    result.content = [content_item]
    result.structured_content = None
    return result


# ---------------------------------------------------------------------------
# AC-4: _mcp_to_anthropic conversion
# ---------------------------------------------------------------------------

class TestMcpToAnthropic:
    def test_mcp_to_anthropic_converts_key_name(self):
        """inputSchema (MCP camelCase) must appear as input_schema (Anthropic snake_case)."""
        schema = {"type": "object", "properties": {"limit": {"type": "integer"}}}
        tool = _make_mock_tool("t", schema=schema)
        result = _mcp_to_anthropic(tool)
        assert "input_schema" in result
        assert "inputSchema" not in result

    def test_mcp_to_anthropic_preserves_schema_content(self):
        schema = {"type": "object", "properties": {"limit": {"type": "integer"}}}
        tool = _make_mock_tool("t", schema=schema)
        result = _mcp_to_anthropic(tool)
        assert result["input_schema"] == schema

    def test_mcp_to_anthropic_keys_present(self):
        tool = _make_mock_tool("my_tool", "does things", {"type": "object", "properties": {}})
        result = _mcp_to_anthropic(tool)
        assert set(result.keys()) == {"name", "description", "input_schema"}

    def test_mcp_to_anthropic_name_and_description_pass_through(self):
        tool = _make_mock_tool("lookup", "Looks things up")
        result = _mcp_to_anthropic(tool)
        assert result["name"] == "lookup"
        assert result["description"] == "Looks things up"

    def test_list_tools_inputSchema_mapped_to_input_schema(self):
        """Key is input_schema not inputSchema in final output."""
        tool = _make_mock_tool("my_tool")
        r = _mcp_to_anthropic(tool)
        assert "input_schema" in r
        assert "inputSchema" not in r

    def test_none_description_becomes_empty_string(self):
        tool = _make_mock_tool("t", description=None)
        result = _mcp_to_anthropic(tool)
        assert result["description"] == ""


# ---------------------------------------------------------------------------
# AC-1/2: list_tools returns Anthropic-format dicts
# ---------------------------------------------------------------------------

class TestListTools:

    @pytest.mark.asyncio
    async def test_list_tools_returns_anthropic_format(self):
        """list_tools() returns dicts with name/description/input_schema."""
        tools = [_make_mock_tool(f"fda_shortage_tool_{i}") for i in range(6)]
        mock_client = _make_mock_client(tools)
        with patch("src.mcp_bridge.Client", return_value=mock_client):
            async with MCPBridge() as bridge:
                result = bridge.list_tools()
        for t in result:
            assert "name" in t
            assert "description" in t
            assert "input_schema" in t
            assert "inputSchema" not in t

    @pytest.mark.asyncio
    async def test_list_tools_returns_all_discovered_tools(self):
        """6 tools if 6 returned by the client."""
        tools = [_make_mock_tool(f"tool_{i}") for i in range(6)]
        mock_client = _make_mock_client(tools)
        with patch("src.mcp_bridge.Client", return_value=mock_client):
            async with MCPBridge() as bridge:
                result = bridge.list_tools()
        assert len(result) == 6

    @pytest.mark.asyncio
    async def test_list_tools_returns_copy(self):
        """Mutating returned list must not affect internal state."""
        tools = [_make_mock_tool(f"tool_{i}") for i in range(6)]
        mock_client = _make_mock_client(tools)
        with patch("src.mcp_bridge.Client", return_value=mock_client):
            async with MCPBridge() as bridge:
                first = bridge.list_tools()
                first.clear()
                second = bridge.list_tools()
        assert len(second) == 6


# ---------------------------------------------------------------------------
# AC-3/routing: call_tool routes to correct server
# ---------------------------------------------------------------------------

class TestCallToolRouting:

    @pytest.mark.asyncio
    async def test_call_tool_routes_to_client(self):
        """call_tool delegates to client.call_tool with correct name and args."""
        mock_client = _make_mock_client(
            [_make_mock_tool("fda_shortage_get_current_shortages")],
            call_result=_make_text_result("result")
        )
        with patch("src.mcp_bridge.Client", return_value=mock_client):
            async with MCPBridge() as bridge:
                await bridge.call_tool("fda_shortage_get_current_shortages", {"limit": 5})
        mock_client.call_tool.assert_called_once_with(
            "fda_shortage_get_current_shortages", {"limit": 5}
        )

    @pytest.mark.asyncio
    async def test_call_tool_unknown_name_raises_value_error(self):
        mock_client = _make_mock_client([_make_mock_tool("real_tool")])
        with patch("src.mcp_bridge.Client", return_value=mock_client):
            async with MCPBridge() as bridge:
                with pytest.raises(ValueError, match="Unknown tool"):
                    await bridge.call_tool("nonexistent_tool", {})


# ---------------------------------------------------------------------------
# AC-5: audit log (tool_calls)
# ---------------------------------------------------------------------------

class TestAuditLog:

    @pytest.mark.asyncio
    async def test_call_tool_appends_to_tool_calls(self):
        mock_client = _make_mock_client(
            [_make_mock_tool("fda_shortage_some_tool")],
            call_result=_make_text_result("hello world")
        )
        with patch("src.mcp_bridge.Client", return_value=mock_client):
            async with MCPBridge() as bridge:
                await bridge.call_tool("fda_shortage_some_tool", {"x": 1})
                log = bridge.tool_calls
        assert len(log) == 1

    @pytest.mark.asyncio
    async def test_tool_call_log_has_required_fields(self):
        """Entry must have: ts, server, tool, args, result_preview, duration_ms."""
        mock_client = _make_mock_client(
            [_make_mock_tool("fda_shortage_some_tool")],
            call_result=_make_text_result("hello world")
        )
        with patch("src.mcp_bridge.Client", return_value=mock_client):
            async with MCPBridge() as bridge:
                await bridge.call_tool("fda_shortage_some_tool", {"x": 1})
                entry = bridge.tool_calls[0]
        for field in ("ts", "server", "tool", "args", "result_preview", "duration_ms"):
            assert field in entry

    @pytest.mark.asyncio
    async def test_tool_call_result_preview_truncated_to_200(self):
        long_text = "x" * 500
        mock_client = _make_mock_client(
            [_make_mock_tool("fda_shortage_tool")],
            call_result=_make_text_result(long_text)
        )
        with patch("src.mcp_bridge.Client", return_value=mock_client):
            async with MCPBridge() as bridge:
                await bridge.call_tool("fda_shortage_tool", {})
                entry = bridge.tool_calls[0]
        assert len(entry["result_preview"]) == 200

    @pytest.mark.asyncio
    async def test_multiple_calls_accumulate_in_tool_calls(self):
        mock_client = _make_mock_client(
            [_make_mock_tool("fda_shortage_t")]
        )
        mock_client.call_tool.side_effect = [
            _make_text_result("r1"),
            _make_text_result("r2"),
            _make_text_result("r3"),
        ]
        with patch("src.mcp_bridge.Client", return_value=mock_client):
            async with MCPBridge() as bridge:
                await bridge.call_tool("fda_shortage_t", {"n": 1})
                await bridge.call_tool("fda_shortage_t", {"n": 2})
                await bridge.call_tool("fda_shortage_t", {"n": 3})
                log = bridge.tool_calls
        assert len(log) == 3


# ---------------------------------------------------------------------------
# AC-4 (schema conversion) — standalone function tests
# ---------------------------------------------------------------------------

class TestSchemaConversion:

    def test_mcp_to_anthropic_converts_key_name(self):
        tool = _make_mock_tool("t")
        result = _mcp_to_anthropic(tool)
        assert "input_schema" in result
        assert "inputSchema" not in result

    def test_mcp_to_anthropic_preserves_schema_content(self):
        schema = {"type": "object", "properties": {"q": {"type": "string"}}}
        tool = _make_mock_tool("t", schema=schema)
        result = _mcp_to_anthropic(tool)
        assert result["input_schema"] == schema


# ---------------------------------------------------------------------------
# AC-7: try/finally cleanup
# ---------------------------------------------------------------------------

class TestCleanup:

    @pytest.mark.asyncio
    async def test_context_manager_calls_aexit_on_clean_exit(self):
        mock_client = _make_mock_client([_make_mock_tool("t")])
        with patch("src.mcp_bridge.Client", return_value=mock_client):
            async with MCPBridge():
                pass
        mock_client.__aexit__.assert_called()

    @pytest.mark.asyncio
    async def test_context_manager_calls_aexit_on_exception(self):
        """Even if list_tools raises, __aexit__ must be called on the client."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.list_tools = AsyncMock(side_effect=RuntimeError("startup failed"))

        with patch("src.mcp_bridge.Client", return_value=mock_client):
            with pytest.raises(RuntimeError, match="startup failed"):
                async with MCPBridge():
                    pass

        mock_client.__aexit__.assert_called()


# ---------------------------------------------------------------------------
# AC-8: collision detection
# ---------------------------------------------------------------------------

class TestCollisionDetection:

    @pytest.mark.asyncio
    async def test_collision_raises_runtime_error(self):
        """Two tools with the same name must raise RuntimeError at startup."""
        tools = [
            _make_mock_tool("shared_name"),
            _make_mock_tool("other_tool"),
            _make_mock_tool("shared_name"),  # duplicate
        ]
        mock_client = _make_mock_client(tools)
        with patch("src.mcp_bridge.Client", return_value=mock_client):
            with pytest.raises(RuntimeError, match="Tool name collision"):
                async with MCPBridge():
                    pass


# ---------------------------------------------------------------------------
# Result extraction
# ---------------------------------------------------------------------------

class TestResultExtraction:

    @pytest.mark.asyncio
    async def test_extract_text_uses_structured_content_when_present(self):
        """When structured_content is present, result must be JSON-serialized."""
        import json as _json
        struct_result = MagicMock()
        struct_result.structured_content = {"result": {"rxcui": "12345"}}
        struct_result.content = []

        mock_client = _make_mock_client(
            [_make_mock_tool("fda_shortage_t")],
            call_result=struct_result
        )
        with patch("src.mcp_bridge.Client", return_value=mock_client):
            async with MCPBridge() as bridge:
                text = await bridge.call_tool("fda_shortage_t", {})
        parsed = _json.loads(text)
        assert parsed == {"rxcui": "12345"}

    @pytest.mark.asyncio
    async def test_extract_text_falls_back_to_content_text(self):
        mock_client = _make_mock_client(
            [_make_mock_tool("fda_shortage_t")],
            call_result=_make_text_result("plain text result")
        )
        with patch("src.mcp_bridge.Client", return_value=mock_client):
            async with MCPBridge() as bridge:
                text = await bridge.call_tool("fda_shortage_t", {})
        assert text == "plain text result"

    @pytest.mark.asyncio
    async def test_extract_text_returns_empty_string_on_empty_result(self):
        empty_result = MagicMock()
        empty_result.structured_content = None
        empty_result.content = []

        mock_client = _make_mock_client(
            [_make_mock_tool("fda_shortage_t")],
            call_result=empty_result
        )
        with patch("src.mcp_bridge.Client", return_value=mock_client):
            async with MCPBridge() as bridge:
                text = await bridge.call_tool("fda_shortage_t", {})
        assert text == ""


# ---------------------------------------------------------------------------
# AC-6: __main__ block exists
# ---------------------------------------------------------------------------

class TestMainBlock:

    def test_main_block_calls_asyncio_run(self):
        """Verify __main__ guard exists in source code."""
        source = Path(__file__).parent.parent / "src" / "mcp_bridge.py"
        text = source.read_text()
        assert 'if __name__ == "__main__"' in text
        assert "asyncio.run(_smoke())" in text

    def test_smoke_function_exists_and_is_async(self):
        from src.mcp_bridge import _smoke
        assert callable(_smoke)
        assert asyncio.iscoroutinefunction(_smoke)
