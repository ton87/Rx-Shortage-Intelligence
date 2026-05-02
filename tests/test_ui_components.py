"""TDD tests for src/ui/components.py and src/ui/formatters.py."""

import pytest

from src.domain.severity import Severity
from src.domain.confidence import Confidence


class TestSeverityBadge:
    def test_critical_badge_contains_class_and_text(self):
        from src.ui.components import severity_badge
        result = severity_badge(Severity.CRITICAL)
        assert "rx-badge-critical" in result
        assert "CRITICAL" in result

    def test_watch_badge(self):
        from src.ui.components import severity_badge
        result = severity_badge(Severity.WATCH)
        assert "rx-badge-watch" in result
        assert "WATCH" in result

    def test_resolved_badge(self):
        from src.ui.components import severity_badge
        result = severity_badge(Severity.RESOLVED)
        assert "rx-badge-resolved" in result
        assert "RESOLVED" in result

    def test_unknown_severity_defaults_to_watch(self):
        from src.ui.components import severity_badge
        result = severity_badge("unknown-value")
        assert "rx-badge-watch" in result

    def test_accepts_plain_string(self):
        from src.ui.components import severity_badge
        result = severity_badge("Critical")
        assert "rx-badge-critical" in result
        assert "CRITICAL" in result


class TestConfidencePill:
    def test_medium_pill_contains_class_and_label(self):
        from src.ui.components import confidence_pill
        result = confidence_pill(Confidence.MEDIUM)
        assert "rx-pill-medium" in result
        assert "MED" in result

    def test_high_pill(self):
        from src.ui.components import confidence_pill
        result = confidence_pill(Confidence.HIGH)
        assert "rx-pill-high" in result

    def test_low_pill(self):
        from src.ui.components import confidence_pill
        result = confidence_pill(Confidence.LOW)
        assert "rx-pill-low" in result

    def test_unknown_confidence_defaults_to_low(self):
        from src.ui.components import confidence_pill
        result = confidence_pill("bogus")
        assert "rx-pill-low" in result

    def test_accepts_plain_string(self):
        from src.ui.components import confidence_pill
        result = confidence_pill("medium")
        assert "rx-pill-medium" in result


class TestCitationLink:
    def test_contains_target_blank(self):
        from src.ui.components import citation_link
        result = citation_link("https://example.com/shortage")
        assert 'target="_blank"' in result

    def test_contains_rel_noopener(self):
        from src.ui.components import citation_link
        result = citation_link("https://example.com/shortage")
        assert 'rel="noopener"' in result

    def test_default_text(self):
        from src.ui.components import citation_link
        result = citation_link("https://example.com/shortage")
        assert "FDA shortage record" in result

    def test_custom_text(self):
        from src.ui.components import citation_link
        result = citation_link("https://example.com", "Custom label")
        assert "Custom label" in result

    def test_url_is_included(self):
        from src.ui.components import citation_link
        result = citation_link("https://example.com/shortage")
        assert "https://example.com/shortage" in result


class TestDemoBanner:
    def test_contains_demo_class(self):
        from src.ui.components import demo_banner
        result = demo_banner()
        assert "rx-demo-banner" in result

    def test_contains_synthetic_label(self):
        from src.ui.components import demo_banner
        result = demo_banner()
        assert "synthetic" in result.lower()
