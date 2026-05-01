"""
Unit tests for H3 (src/agent.py) and H4 (src/briefing.py).
Pure unit tests — no network, no MCP, no real API calls.
"""

import asyncio
import json
import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_text_block(text: str):
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def _make_tool_use_block(tool_id: str, name: str, input_: dict):
    block = MagicMock()
    block.type = "tool_use"
    block.id = tool_id
    block.name = name
    block.input = input_
    return block


def _make_response(stop_reason: str, content: list):
    resp = MagicMock()
    resp.stop_reason = stop_reason
    resp.content = content
    return resp


# ---------------------------------------------------------------------------
# Tests: compute_diff
# ---------------------------------------------------------------------------

from src.briefing import compute_diff, index_formulary, index_orders, build_user_message, parse_briefing_item


class TestComputeDiff(unittest.TestCase):

    def _make_shortage(self, rxcui_list, status, name="TestDrug"):
        return {"rxcui": rxcui_list, "status": status, "generic_name": name}

    def test_new_drug_in_today_not_yesterday(self):
        today = [self._make_shortage(["A"], "Current")]
        yesterday = []
        result = compute_diff(today, yesterday, {"A"})
        self.assertEqual(len(result["new"]), 1)
        self.assertEqual(result["new"][0]["_diff_bucket"], "new")
        self.assertEqual(len(result["resolved"]), 0)

    def test_resolved_in_yesterday_not_today(self):
        today = []
        yesterday = [self._make_shortage(["A"], "Current")]
        result = compute_diff(today, yesterday, {"A"})
        self.assertEqual(len(result["resolved"]), 1)
        self.assertEqual(result["resolved"][0]["_diff_bucket"], "resolved")
        self.assertEqual(len(result["new"]), 0)

    def test_escalated_when_status_worsens(self):
        # Resolved (rank 0) → Current (rank 2): escalated
        today = [self._make_shortage(["A"], "Current")]
        yesterday = [self._make_shortage(["A"], "Resolved")]
        result = compute_diff(today, yesterday, {"A"})
        self.assertEqual(len(result["escalated"]), 1)
        self.assertEqual(result["escalated"][0]["_diff_bucket"], "escalated")

    def test_improved_when_status_improves(self):
        # Current (rank 2) → Resolved (rank 0): improved
        today = [self._make_shortage(["A"], "Resolved")]
        yesterday = [self._make_shortage(["A"], "Current")]
        result = compute_diff(today, yesterday, {"A"})
        self.assertEqual(len(result["improved"]), 1)
        self.assertEqual(result["improved"][0]["_diff_bucket"], "improved")

    def test_unchanged_same_status(self):
        today = [self._make_shortage(["A"], "Current")]
        yesterday = [self._make_shortage(["A"], "Current")]
        result = compute_diff(today, yesterday, {"A"})
        self.assertEqual(len(result["unchanged"]), 1)
        self.assertEqual(result["unchanged"][0]["_diff_bucket"], "unchanged")

    def test_diff_skips_drugs_not_in_formulary(self):
        today = [self._make_shortage(["NONFORMULARY"], "Current")]
        yesterday = []
        result = compute_diff(today, yesterday, {"FORMULARY_ONLY"})
        self.assertEqual(len(result["new"]), 0)
        self.assertEqual(len(result["escalated"]), 0)
        self.assertEqual(len(result["improved"]), 0)
        self.assertEqual(len(result["unchanged"]), 0)

    def test_fda_rxcui_list_matched_correctly(self):
        # Drug has rxcui=["A","B"], formulary has "B" → should match
        today = [self._make_shortage(["A", "B"], "Current")]
        yesterday = []
        result = compute_diff(today, yesterday, {"B"})
        self.assertEqual(len(result["new"]), 1)
        self.assertEqual(result["new"][0]["_formulary_rxcui"], "B")

    def test_diff_bucket_set_on_items(self):
        today = [
            self._make_shortage(["A"], "Current"),
            self._make_shortage(["B"], "Resolved"),
        ]
        yesterday = [
            self._make_shortage(["B"], "Current"),
        ]
        formulary = {"A", "B"}
        result = compute_diff(today, yesterday, formulary)
        for bucket in result.values():
            for item in bucket:
                self.assertIn("_diff_bucket", item)

    def test_formulary_rxcui_set_on_items(self):
        today = [self._make_shortage(["A", "B"], "Current")]
        yesterday = []
        result = compute_diff(today, yesterday, {"A", "B"})
        for item in result["new"]:
            self.assertIn("_formulary_rxcui", item)


# ---------------------------------------------------------------------------
# Tests: parse_briefing_item
# ---------------------------------------------------------------------------

class TestParseBriefingItem(unittest.TestCase):

    def test_parses_valid_json_from_agent_text(self):
        payload = {"rxcui": "123", "drug_name": "Aspirin", "severity": "Watch",
                   "summary": "test", "rationale": "r", "alternatives": [],
                   "citations": [], "confidence": "high", "recommended_action": "act",
                   "tool_call_log": []}
        result = parse_briefing_item(json.dumps(payload), "Aspirin", "123")
        self.assertEqual(result["rxcui"], "123")
        self.assertEqual(result["severity"], "Watch")

    def test_falls_back_on_invalid_json(self):
        result = parse_briefing_item("not json at all", "Aspirin", "123")
        self.assertEqual(result["rxcui"], "123")
        self.assertEqual(result["drug_name"], "Aspirin")
        self.assertEqual(result["confidence"], "low")

    def test_fallback_has_confidence_low(self):
        result = parse_briefing_item("{bad json", "DrugX", "456")
        self.assertEqual(result["confidence"], "low")

    def test_extracts_json_from_text_with_prose(self):
        payload = {"rxcui": "999", "drug_name": "Test", "severity": "Critical",
                   "summary": "s", "rationale": "r", "alternatives": [],
                   "citations": [], "confidence": "high", "recommended_action": "act",
                   "tool_call_log": []}
        text = "Here is my analysis:\n\n" + json.dumps(payload) + "\n\nEnd."
        result = parse_briefing_item(text, "Test", "999")
        self.assertEqual(result["severity"], "Critical")
        self.assertEqual(result["rxcui"], "999")

    def test_fallback_includes_text_in_rationale(self):
        text = "Some partial output from the agent."
        result = parse_briefing_item(text, "DrugY", "789")
        self.assertIn("Some partial output", result["rationale"])

    def test_empty_text_fallback(self):
        result = parse_briefing_item("", "DrugZ", "000")
        self.assertEqual(result["rationale"], "No output.")
        self.assertEqual(result["confidence"], "low")


# ---------------------------------------------------------------------------
# Tests: build_user_message
# ---------------------------------------------------------------------------

class TestBuildUserMessage(unittest.TestCase):

    def _drug(self, rxcui="123", name="TestDrug", status="Current", bucket="new"):
        return {
            "_formulary_rxcui": rxcui,
            "generic_name": name,
            "status": status,
            "_diff_bucket": bucket,
        }

    def _formulary(self, status="preferred", route="IV", alts=None):
        return {
            "formulary_status": status,
            "route_of_administration": route,
            "preferred_alternatives": alts or [],
            "name": "FormularyDrug",
        }

    def _orders(self, count=5, departments=None):
        return {"count_last_30_days": count, "departments": departments or ["ICU"]}

    def test_includes_drug_name_and_rxcui(self):
        msg = build_user_message(
            self._drug(rxcui="999", name="Cisplatin"),
            self._formulary(), self._orders(), "Current", ""
        )
        self.assertIn("Cisplatin", msg)
        self.assertIn("999", msg)

    def test_includes_order_count(self):
        msg = build_user_message(
            self._drug(), self._formulary(), self._orders(count=42), "Current", ""
        )
        self.assertIn("42", msg)

    def test_handles_missing_orders_gracefully(self):
        msg = build_user_message(
            self._drug(), self._formulary(), None, "Current", ""
        )
        self.assertIn("0", msg)
        self.assertIn("none recorded", msg)

    def test_includes_diff_bucket(self):
        msg = build_user_message(
            self._drug(bucket="escalated"), self._formulary(), self._orders(), "Current", "Resolved"
        )
        self.assertIn("escalated", msg)

    def test_includes_yesterday_status(self):
        msg = build_user_message(
            self._drug(), self._formulary(), self._orders(), "Current", "Resolved"
        )
        self.assertIn("Resolved", msg)

    def test_uses_formulary_name_when_generic_name_missing(self):
        drug = {"_formulary_rxcui": "123", "_diff_bucket": "new", "status": "Current"}
        formulary = {"formulary_status": "preferred", "route_of_administration": "IV",
                     "preferred_alternatives": [], "name": "FallbackName"}
        msg = build_user_message(drug, formulary, None, "Current", "")
        self.assertIn("FallbackName", msg)


# ---------------------------------------------------------------------------
# Tests: index_formulary / index_orders
# ---------------------------------------------------------------------------

class TestIndexFunctions(unittest.TestCase):

    def test_index_formulary_by_all_rxcuis_in_list(self):
        drugs = [
            {"rxcui": "A", "rxcui_list": ["A", "B", "C"], "name": "DrugA"},
            {"rxcui": "D", "rxcui_list": ["D"], "name": "DrugD"},
        ]
        idx = index_formulary(drugs)
        self.assertIn("A", idx)
        self.assertIn("B", idx)
        self.assertIn("C", idx)
        self.assertIn("D", idx)
        self.assertEqual(idx["B"]["name"], "DrugA")

    def test_index_formulary_falls_back_to_rxcui_key(self):
        drugs = [{"rxcui": "X", "name": "DrugX"}]  # no rxcui_list
        idx = index_formulary(drugs)
        self.assertIn("X", idx)

    def test_index_formulary_skips_empty_rxcui(self):
        drugs = [{"rxcui": "", "rxcui_list": ["", None], "name": "Bad"}]
        idx = index_formulary(drugs)
        self.assertEqual(len(idx), 0)

    def test_index_orders_by_rxcui(self):
        orders = [
            {"rxcui": "111", "count_last_30_days": 5},
            {"rxcui": "222", "count_last_30_days": 10},
        ]
        idx = index_orders(orders)
        self.assertIn("111", idx)
        self.assertEqual(idx["222"]["count_last_30_days"], 10)

    def test_index_orders_skips_missing_rxcui(self):
        orders = [{"count_last_30_days": 5}]  # no rxcui key
        idx = index_orders(orders)
        self.assertEqual(len(idx), 0)


# ---------------------------------------------------------------------------
# Tests: run_agent (mock anthropic)
# ---------------------------------------------------------------------------

from src.agent import run_agent, MAX_ITERATIONS


class TestRunAgent(unittest.IsolatedAsyncioTestCase):

    def _make_client_mock(self, responses):
        """responses: list of (stop_reason, content_blocks)"""
        client_mock = MagicMock()
        side_effects = [_make_response(sr, content) for sr, content in responses]
        client_mock.messages.create.side_effect = side_effects
        return client_mock

    async def test_run_agent_returns_text_on_end_turn(self):
        text_block = _make_text_block("Final answer.")
        client_mock = self._make_client_mock([("end_turn", [text_block])])

        with patch("src.agent.anthropic.Anthropic", return_value=client_mock):
            text, log = await run_agent(
                system=[{"type": "text", "text": "sys"}],
                user_msg="hello",
                tools=[],
                call_tool_fn=AsyncMock(return_value="{}"),
            )

        self.assertEqual(text, "Final answer.")
        self.assertEqual(log, [])

    async def test_run_agent_calls_tool_on_tool_use(self):
        tool_block = _make_tool_use_block("id1", "my_tool", {"arg": "val"})
        text_block = _make_text_block("Done.")
        tool_resp = _make_response("tool_use", [tool_block])
        end_resp = _make_response("end_turn", [text_block])
        client_mock = self._make_client_mock([
            ("tool_use", [tool_block]),
            ("end_turn", [text_block]),
        ])
        call_tool = AsyncMock(return_value='{"result": "ok"}')

        with patch("src.agent.anthropic.Anthropic", return_value=client_mock):
            text, log = await run_agent(
                system=[],
                user_msg="use the tool",
                tools=[],
                call_tool_fn=call_tool,
            )

        call_tool.assert_awaited_once_with("my_tool", {"arg": "val"})
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]["tool"], "my_tool")
        self.assertEqual(text, "Done.")

    async def test_run_agent_respects_max_iterations(self):
        # Always returns tool_use → should hit iteration cap and return ("", log)
        tool_block = _make_tool_use_block("id1", "loop_tool", {})
        responses = [("tool_use", [tool_block])] * (MAX_ITERATIONS + 5)
        client_mock = self._make_client_mock(responses)
        call_tool = AsyncMock(return_value="{}")

        with patch("src.agent.anthropic.Anthropic", return_value=client_mock):
            text, log = await run_agent(
                system=[],
                user_msg="go",
                tools=[],
                call_tool_fn=call_tool,
            )

        self.assertEqual(text, "")
        self.assertEqual(client_mock.messages.create.call_count, MAX_ITERATIONS)

    async def test_run_agent_handles_tool_exception_gracefully(self):
        tool_block = _make_tool_use_block("id1", "bad_tool", {})
        text_block = _make_text_block("Handled error.")
        client_mock = self._make_client_mock([
            ("tool_use", [tool_block]),
            ("end_turn", [text_block]),
        ])

        async def failing_tool(name, args):
            raise RuntimeError("Network failure")

        with patch("src.agent.anthropic.Anthropic", return_value=client_mock):
            text, log = await run_agent(
                system=[],
                user_msg="call bad tool",
                tools=[],
                call_tool_fn=failing_tool,
            )

        self.assertEqual(len(log), 1)
        result_preview = log[0]["result_preview"]
        self.assertIn("error", result_preview.lower())
        self.assertEqual(text, "Handled error.")

    async def test_run_agent_appends_to_tool_call_log(self):
        tool1 = _make_tool_use_block("id1", "tool_a", {"x": 1})
        tool2 = _make_tool_use_block("id2", "tool_b", {"y": 2})
        text_block = _make_text_block("All done.")
        client_mock = self._make_client_mock([
            ("tool_use", [tool1, tool2]),
            ("end_turn", [text_block]),
        ])
        call_tool = AsyncMock(return_value='{"ok": true}')

        with patch("src.agent.anthropic.Anthropic", return_value=client_mock):
            text, log = await run_agent(
                system=[],
                user_msg="run two tools",
                tools=[],
                call_tool_fn=call_tool,
            )

        self.assertEqual(len(log), 2)
        self.assertEqual(log[0]["tool"], "tool_a")
        self.assertEqual(log[1]["tool"], "tool_b")

    async def test_run_agent_non_tool_stop_reason_breaks_loop(self):
        # stop_reason="max_tokens" should break immediately and return ("", [])
        resp = _make_response("max_tokens", [])
        client_mock = self._make_client_mock([("max_tokens", [])])
        call_tool = AsyncMock(return_value="{}")

        with patch("src.agent.anthropic.Anthropic", return_value=client_mock):
            text, log = await run_agent(
                system=[],
                user_msg="test",
                tools=[],
                call_tool_fn=call_tool,
            )

        self.assertEqual(text, "")
        self.assertEqual(log, [])
        self.assertEqual(client_mock.messages.create.call_count, 1)

    async def test_run_agent_result_preview_truncated(self):
        long_result = "x" * 500
        tool_block = _make_tool_use_block("id1", "big_tool", {})
        text_block = _make_text_block("ok")
        client_mock = self._make_client_mock([
            ("tool_use", [tool_block]),
            ("end_turn", [text_block]),
        ])
        call_tool = AsyncMock(return_value=long_result)

        with patch("src.agent.anthropic.Anthropic", return_value=client_mock):
            _, log = await run_agent(
                system=[],
                user_msg="x",
                tools=[],
                call_tool_fn=call_tool,
            )

        self.assertEqual(len(log[0]["result_preview"]), 200)


if __name__ == "__main__":
    unittest.main()
