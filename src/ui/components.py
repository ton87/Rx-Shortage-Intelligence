"""HTML emitters used across UI tabs. Each function knows class names from
src/ui/theme.css and nothing else.
"""

import html

from src.domain.confidence import Confidence, CONFIDENCE_LABELS
from src.domain.severity import Severity


def severity_badge(severity: str | Severity) -> str:
    s = str(severity).strip()
    cls = s.lower() if s.lower() in {"critical", "watch", "resolved"} else "watch"
    return f'<span class="rx-badge rx-badge-{cls}">{html.escape(s.upper())}</span>'


def confidence_pill(conf: str | Confidence) -> str:
    c = str(conf).strip().lower()
    if c not in {"high", "medium", "low"}:
        c = "low"
    label = CONFIDENCE_LABELS[Confidence(c)]
    return f'<span class="rx-pill rx-pill-{c}">{label}</span>'


def citation_link(url: str, text: str = "FDA shortage record") -> str:
    return (
        f'<a href="{html.escape(url)}" target="_blank" rel="noopener">{html.escape(text)}</a>'
    )


def demo_banner() -> str:
    return (
        '<div class="rx-demo-banner">'
        '<span class="rx-demo-chip">DEMO</span>'
        '<span>Formulary and active orders are synthetic. '
        'FDA shortage feed and RxNorm are live public data.</span>'
        '</div>'
    )
