"""
correction_result.py — Hydra Brain v0.5.0
==========================================

The history and result of self-correction loops.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List

from core.results.base import BaseResult
from core.results.consensus_result import ConsensusResult
from core.results.verification_result import VerificationResult


@dataclass(kw_only=True)
class CorrectionResult(BaseResult):
    """The result of executing a self-correction loop."""
    final_consensus: ConsensusResult
    final_verification: VerificationResult
    passed: bool
    attempts: int
    attempt_log: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "final_consensus": self.final_consensus.to_dict(),
            "final_verification": self.final_verification.to_dict(),
            "passed": self.passed,
            "attempts": self.attempts,
            "attempt_log": self.attempt_log,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }
