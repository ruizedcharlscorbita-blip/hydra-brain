"""
confidence_result.py — Hydra Brain v0.5.0
==========================================

The outcome of confidence scoring.
"""

from dataclasses import dataclass
from typing import Any, Dict

from core.results.base import BaseResult


@dataclass(kw_only=True)
class ConfidenceScore(BaseResult):
    """The outcome of confidence scoring."""
    final_score: float
    consensus_component: float
    verification_component: float
    routing_component: float
    label: str  # "HIGH" / "MEDIUM" / "LOW" / "UNCERTAIN"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "final_score": round(self.final_score, 6),
            "consensus_component": round(self.consensus_component, 6),
            "verification_component": round(self.verification_component, 6),
            "routing_component": round(self.routing_component, 6),
            "label": self.label,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }
