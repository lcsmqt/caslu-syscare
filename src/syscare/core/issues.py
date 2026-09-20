"""Common finding type shared by all diagnostic modules (feeds reports and recommendations)."""
from __future__ import annotations

from dataclasses import dataclass, asdict

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}
SEVERITY_LABEL = {"high": "ALTA", "medium": "MÉDIA", "low": "BAIXA", "info": "INFO"}


@dataclass
class Issue:
    area: str
    severity: str          # high | medium | low | info
    title: str
    detail: str = ""
    recommendation: str = ""
    evidence: str = ""     # the measured value(s) the finding is based on

    def to_dict(self) -> dict:
        return asdict(self)


def sort_issues(issues: list[Issue]) -> list[Issue]:
    return sorted(issues, key=lambda i: SEVERITY_ORDER.get(i.severity, 9))
