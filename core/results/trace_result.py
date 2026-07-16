"""
trace_result.py — Hydra Brain v0.5.0
=====================================

The execution trace object capturing the decision graph and execution history
of a single Hydra orchestration run.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

from core.results.base import BaseResult


@dataclass(kw_only=True)
class HydraTrace(BaseResult):
    """
    Captures the step-by-step telemetry of how a prompt was routed, executed,
    and verified. Primarily used for observability, benchmarking, and debugging.
    """
    intent: str
    intent_weights: Dict[str, float]
    eligible_models: List[str]
    ranked_models: List[Tuple[float, str]]  # list of (score, model_id)
    attempt_log: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent,
            "intent_weights": self.intent_weights,
            "eligible_models": self.eligible_models,
            "ranked_models": self.ranked_models,
            "attempt_log": self.attempt_log,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }
