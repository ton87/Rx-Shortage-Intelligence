"""
Unit tests for H6 eval harness — no LLM calls, fully deterministic.
"""

import pytest
from src.eval.runner import (
    load_cases,
    score_severity,
    score_citations,
    score_hallucination,
    aggregate_scores,
    run_suite,
    _make_synthetic_actual,
)


# ── load_cases ────────────────────────────────────────────────────────────────

def test_load_cases_returns_list():
    cases = load_cases()
    assert isinstance(cases, list)


def test_load_cases_has_15_cases():
    cases = load_cases()
    assert len(cases) == 15


# ── score_severity ────────────────────────────────────────────────────────────

def test_score_severity_correct_match():
    case = {"expected": {"severity": "Critical"}}
    actual = {"severity": "Critical"}
    assert score_severity(case, actual) == 1.0


def test_score_severity_mismatch():
    case = {"expected": {"severity": "Critical"}}
    actual = {"severity": "Watch"}
    assert score_severity(case, actual) == 0.0


# ── score_citations ───────────────────────────────────────────────────────────

def test_score_citations_all_have_url():
    actual = {
        "citations": [
            {"claim": "drug in shortage", "url": "https://example.com/1"},
            {"claim": "label info", "url": "https://example.com/2"},
        ]
    }
    assert score_citations(actual) == 1.0


def test_score_citations_none_returns_zero():
    actual = {"citations": []}
    assert score_citations(actual) == 0.0


def test_score_citations_partial():
    actual = {
        "citations": [
            {"claim": "drug in shortage", "url": "https://example.com/1"},
            {"claim": "no url here", "url": ""},
        ]
    }
    result = score_citations(actual)
    assert result == 0.5


# ── score_hallucination ───────────────────────────────────────────────────────

def test_score_hallucination_clean():
    actual = {
        "severity": "Critical",
        "confidence": "high",
        "rxcui": "12345",
        "drug_name": "cisplatin",
    }
    assert score_hallucination(actual) == 0.0


def test_score_hallucination_invalid_severity():
    actual = {
        "severity": "VERY BAD",  # invalid
        "confidence": "high",
        "rxcui": "12345",
        "drug_name": "cisplatin",
    }
    assert score_hallucination(actual) == 1.0


def test_score_hallucination_missing_rxcui():
    actual = {
        "severity": "Watch",
        "confidence": "medium",
        "rxcui": "",  # empty
        "drug_name": "morphine",
    }
    assert score_hallucination(actual) == 1.0


# ── aggregate_scores ──────────────────────────────────────────────────────────

def test_aggregate_scores_computes_means():
    results = [
        {
            "scores": {
                "severity_accuracy": 1.0,
                "citation_accuracy": 1.0,
                "hallucination_rate": 0.0,
                "recall": 1.0,
                "clinical_appropriateness": 4.0,
            }
        },
        {
            "scores": {
                "severity_accuracy": 0.0,
                "citation_accuracy": 0.5,
                "hallucination_rate": 0.0,
                "recall": 1.0,
                "clinical_appropriateness": 4.0,
            }
        },
    ]
    agg = aggregate_scores(results)
    assert agg["severity_accuracy"] == 0.5
    assert agg["citation_accuracy"] == 0.75
    assert agg["hallucination_rate"] == 0.0
    assert agg["recall"] == 1.0
    assert agg["clinical_appropriateness"] == 4.0


def test_aggregate_scores_hallucination_pass():
    results = [
        {
            "scores": {
                "severity_accuracy": 1.0,
                "citation_accuracy": 1.0,
                "hallucination_rate": 0.0,
                "recall": 1.0,
                "clinical_appropriateness": 4.0,
            }
        }
    ]
    agg = aggregate_scores(results)
    assert agg["hallucination_pass"] is True
    assert agg["severity_pass"] is True
    assert agg["citation_pass"] is True


# ── run_suite ─────────────────────────────────────────────────────────────────

def test_run_suite_returns_expected_shape():
    result = run_suite("v1")
    assert "prompt_version" in result
    assert "run_timestamp" in result
    assert "case_count" in result
    assert "results" in result
    assert "aggregate" in result
    assert result["prompt_version"] == "v1"


def test_run_suite_case_count_equals_15():
    result = run_suite("v1")
    assert result["case_count"] == 15
    assert len(result["results"]) == 15


# ── _make_synthetic_actual ────────────────────────────────────────────────────

def test_make_synthetic_actual_uses_expected_severity():
    case = {
        "case_id": "C-99",
        "input": {
            "rxcui": "99999",
            "drug_name": "testdrug",
            "diff_bucket": "new",
        },
        "expected": {
            "severity": "Critical",
            "min_confidence": "high",
        },
    }
    actual = _make_synthetic_actual(case)
    assert actual["severity"] == "Critical"
    assert actual["rxcui"] == "99999"
    assert actual["drug_name"] == "testdrug"
    assert actual["confidence"] == "high"
    assert len(actual["citations"]) > 0
