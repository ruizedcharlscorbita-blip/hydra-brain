"""
verification_result.py — Hydra Brain v0.5.0
============================================

Verification results and constraint checks definitions.
"""

from dataclasses import dataclass
from typing import Any, Dict, List

from core.results.base import BaseResult


@dataclass
class CheckResult:
    """The result of evaluating a single constraint."""
    constraint_name: str
    passed: bool
    reason: str


@dataclass(kw_only=True)
class VerificationResult(BaseResult):
    """The outcome of running the verification engine on a response."""
    passed: bool
    checks: List[CheckResult]
    score: float
    model_id: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "score": round(self.score, 6),
            "model_id": self.model_id,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
            "checks": [
                {
                    "constraint_name": c.constraint_name,
                    "passed": c.passed,
                    "reason": c.reason
                } for c in self.checks
            ]
        }
