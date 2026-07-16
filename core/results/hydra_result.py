"""
hydra_result.py — Hydra Brain v0.5.0
=====================================

The top-level result envelope returned by HydraController's execute_and_verify.
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional

from core.results.base import BaseResult
from core.results.execution_result import ExecutionResult
from core.results.consensus_result import ConsensusResult
from core.results.verification_result import VerificationResult
from core.results.confidence_result import ConfidenceScore
from core.results.correction_result import CorrectionResult
from core.results.trace_result import HydraTrace


@dataclass(kw_only=True)
class HydraResult(BaseResult):
    """
    Top-level output of the execute_and_verify pipeline.
    """
    response: str
    passed: bool
    attempts: int
    execution: ExecutionResult
    consensus: ConsensusResult
    verification: VerificationResult
    confidence: ConfidenceScore
    correction: Optional[CorrectionResult] = None
    trace: Optional[HydraTrace] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "response": self.response,
            "passed": self.passed,
            "attempts": self.attempts,
            "execution": self.execution.to_dict(),
            "consensus": self.consensus.to_dict(),
            "verification": self.verification.to_dict(),
            "confidence": self.confidence.to_dict(),
            "correction": self.correction.to_dict() if self.correction else None,
            "trace": self.trace.to_dict() if self.trace else None,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    def __repr__(self) -> str:
        status = "PASSED" if self.passed else "FAILED"
        return (
            f"HydraResult(passed={status}, attempts={self.attempts}, "
            f"winner={self.execution.model_id!r}, "
            f"confidence={self.confidence.label} ({self.confidence.final_score:.3f}))"
        )
