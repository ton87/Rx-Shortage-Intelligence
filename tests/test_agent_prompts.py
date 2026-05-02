"""
TDD tests for src/agent/prompts.py — loader, builders, and parser.

These tests must pass after Task 4.3 is implemented. They validate:
1. load_prompt returns non-empty, byte-stable strings matching baseline hashes.
2. build_system_blocks returns exactly 4 cacheable blocks.
3. parse_briefing_item extracts valid JSON from agent output.
4. parse_briefing_item falls back gracefully on garbage input.
"""

import hashlib
import json
import unittest

# R2 baseline hashes from docs/superpowers/plans/baseline-2026-05-01.md
ROLE_HASH = "68f482f157934367850cafef4bde40e4c58fc2fbd725505a14af2d358750df9a"
RUBRIC_HASH = "802ae28a8aa0d062c6b32d52b85dd0ac8733de475d96fbbd6f886ea73024b00c"


class TestLoadPrompt(unittest.TestCase):
    """load_prompt returns non-empty, byte-stable strings."""

    def setUp(self):
        from src.agent.prompts import load_prompt
        self.load_prompt = load_prompt

    def test_load_role_and_rules_non_empty(self):
        text = self.load_prompt("role_and_rules")
        self.assertIsInstance(text, str)
        self.assertGreater(len(text), 100)

    def test_load_severity_rubric_non_empty(self):
        text = self.load_prompt("severity_rubric")
        self.assertIsInstance(text, str)
        self.assertGreater(len(text), 100)

    def test_role_hash_matches_baseline(self):
        """R2 mitigation: byte-stable hash must match pre-restructure baseline."""
        text = self.load_prompt("role_and_rules")
        got = hashlib.sha256(text.encode()).hexdigest()
        self.assertEqual(got, ROLE_HASH, f"ROLE_AND_RULES hash drifted: {got}")

    def test_rubric_hash_matches_baseline(self):
        """R2 mitigation: byte-stable hash must match pre-restructure baseline."""
        text = self.load_prompt("severity_rubric")
        got = hashlib.sha256(text.encode()).hexdigest()
        self.assertEqual(got, RUBRIC_HASH, f"SEVERITY_RUBRIC hash drifted: {got}")


class TestBuildSystemBlocks(unittest.TestCase):
    """build_system_blocks returns 4 cacheable blocks in the correct order."""

    def setUp(self):
        from src.agent.prompts import build_system_blocks
        self.build_system_blocks = build_system_blocks

    def _sample_formulary(self):
        return [{"rxcui": "12345", "name": "TestDrug", "formulary_status": "preferred"}]

    def test_returns_exactly_4_blocks(self):
        blocks = self.build_system_blocks(self._sample_formulary())
        self.assertEqual(len(blocks), 4)

    def test_all_blocks_are_dicts_with_type_text(self):
        blocks = self.build_system_blocks(self._sample_formulary())
        for b in blocks:
            self.assertIsInstance(b, dict)
            self.assertEqual(b["type"], "text")

    def test_all_blocks_have_cache_control(self):
        blocks = self.build_system_blocks(self._sample_formulary())
        for b in blocks:
            self.assertIn("cache_control", b)
            self.assertEqual(b["cache_control"]["type"], "ephemeral")

    def test_first_block_is_role_and_rules(self):
        blocks = self.build_system_blocks(self._sample_formulary())
        # First block should contain the ROLE_AND_RULES content
        self.assertIn("clinical pharmacy intelligence agent", blocks[0]["text"])

    def test_second_block_is_severity_rubric(self):
        blocks = self.build_system_blocks(self._sample_formulary())
        # Second block should contain the SEVERITY_RUBRIC content
        self.assertIn("deterministic backbone", blocks[1]["text"])

    def test_third_block_contains_formulary_json(self):
        blocks = self.build_system_blocks(self._sample_formulary())
        self.assertIn("FORMULARY SUBSET", blocks[2]["text"])
        self.assertIn("TestDrug", blocks[2]["text"])

    def test_fourth_block_is_prefetch_override(self):
        blocks = self.build_system_blocks(self._sample_formulary())
        self.assertIn("PREFETCH MODE", blocks[3]["text"])


class TestParseBriefingItem(unittest.TestCase):
    """parse_briefing_item extracts JSON and falls back gracefully."""

    def setUp(self):
        from src.agent.prompts import parse_briefing_item
        self.parse_briefing_item = parse_briefing_item

    def _valid_item_json(self):
        return json.dumps({
            "rxcui": "12345",
            "drug_name": "TestDrug",
            "severity": "Critical",
            "summary": "Shortage detected.",
            "rationale": "Rule C1 matched.",
            "alternatives": [],
            "citations": [],
            "confidence": "high",
            "recommended_action": "Contact pharmacy.",
            "tool_call_log": [],
        })

    def test_extracts_valid_json_object(self):
        text = f"Some preamble text.\n{self._valid_item_json()}\nSome trailing prose."
        result = self.parse_briefing_item(text, "TestDrug", "12345")
        self.assertEqual(result["rxcui"], "12345")
        self.assertEqual(result["severity"], "Critical")

    def test_returns_dict_on_bare_json(self):
        text = self._valid_item_json()
        result = self.parse_briefing_item(text, "TestDrug", "12345")
        self.assertIsInstance(result, dict)
        self.assertEqual(result["drug_name"], "TestDrug")

    def test_fallback_on_empty_string(self):
        result = self.parse_briefing_item("", "FallbackDrug", "99999")
        self.assertIsInstance(result, dict)
        self.assertEqual(result["rxcui"], "99999")
        self.assertEqual(result["drug_name"], "FallbackDrug")
        self.assertEqual(result["confidence"], "low")

    def test_fallback_on_garbage_input(self):
        result = self.parse_briefing_item("not json at all !!!", "GarbageDrug", "00000")
        self.assertIsInstance(result, dict)
        self.assertEqual(result["drug_name"], "GarbageDrug")
        self.assertEqual(result["confidence"], "low")
        self.assertIn("recommended_action", result)


if __name__ == "__main__":
    unittest.main()
