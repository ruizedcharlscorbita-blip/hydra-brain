"""
consensus_result.py — Hydra Brain v0.5.0
========================================

The outcome of consensus evaluation across multiple execution attempts.
"""

from dataclasses import dataclass
from typing import Any, Dict, List

from core.results.base import BaseResult
from core.results.execution_result import ExecutionResult


@dataclass(kw_only=True)
class ConsensusResult(BaseResult):
    """
    ConsensusResult envelopes the outcome of evaluating multiple executions.
    """
    winner: ExecutionResult
    successful: List[ExecutionResult]
    failed: List[ExecutionResult]
    strategy: str
    consensus_score: float

    @property
    def successful_count(self) -> int:
        return len(self.successful)

    @property
    def failed_count(self) -> int:
        return len(self.failed)

    @property
    def total_count(self) -> int:
        return self.successful_count + self.failed_count

    def to_dict(self) -> Dict[str, Any]:
        return {
            "winner": self.winner.to_dict(),
            "strategy": self.strategy,
            "consensus_score": round(self.consensus_score, 6),
            "successful_count": self.successful_count,
            "failed_count": self.failed_count,
            "total_count": self.total_count,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
            "all_model_ids": [r.model_id for r in (self.successful + self.failed)],
            "failed_model_ids": [r.model_id for r in self.failed],
        }

    def __repr__(self) -> str:
        return (
            f"ConsensusResult(winner={self.winner.model_id!r}, "
            f"strategy={self.strategy!r}, "
            f"score={self.consensus_score:.3f}, "
            f"{self.successful_count}/{self.total_count} succeeded)"
        )
