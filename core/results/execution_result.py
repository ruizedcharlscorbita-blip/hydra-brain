"""
execution_result.py — Hydra Brain v0.5.0
==========================================

The canonical result envelope for a single model completion attempt.
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional

from core.results.base import BaseResult


@dataclass(kw_only=True)
class ExecutionResult(BaseResult):
    """
    Canonical result envelope for a single model invocation.
    """
    model_id: str
    provider: str
    response: Optional[str]
    success: bool
    latency_ms: int
    http_status: Optional[int] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    routing_score: float = 0.0
    capability_confidence: str = "none"
    attempt: int = 1

    @classmethod
    def from_failure(
        cls,
        model_id: str,
        provider: str,
        latency_ms: int,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        http_status: Optional[int] = None,
        routing_score: float = 0.0,
        capability_confidence: str = "none",
        attempt: int = 1,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "ExecutionResult":
        res = cls(
            model_id=model_id,
            provider=provider,
            response=None,
            success=False,
            latency_ms=latency_ms,
            http_status=http_status,
            error_code=error_code,
            error_message=error_message,
            routing_score=routing_score,
            capability_confidence=capability_confidence,
            attempt=attempt,
        )
        if metadata:
            res.metadata = metadata
        return res

    @classmethod
    def from_success(
        cls,
        model_id: str,
        provider: str,
        response: str,
        latency_ms: int,
        http_status: int = 200,
        routing_score: float = 0.0,
        capability_confidence: str = "none",
        attempt: int = 1,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "ExecutionResult":
        res = cls(
            model_id=model_id,
            provider=provider,
            response=response,
            success=True,
            latency_ms=latency_ms,
            http_status=http_status,
            routing_score=routing_score,
            capability_confidence=capability_confidence,
            attempt=attempt,
        )
        if metadata:
            res.metadata = metadata
        return res

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "provider": self.provider,
            "success": self.success,
            "latency_ms": self.latency_ms,
            "http_status": self.http_status,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "routing_score": round(self.routing_score, 6),
            "capability_confidence": self.capability_confidence,
            "attempt": self.attempt,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
            "response_preview": (self.response[:120] + "...") if self.response and len(self.response) > 120 else self.response,
        }

    @property
    def response_length(self) -> int:
        return len(self.response) if self.response else 0

    @property
    def is_empty_response(self) -> bool:
        return self.success and (not self.response or not self.response.strip())

    def __repr__(self) -> str:
        status = "OK" if self.success else f"FAIL({self.error_code})"
        return (
            f"ExecutionResult({self.model_id!r}, {status}, "
            f"latency={self.latency_ms}ms, score={self.routing_score:.3f})"
        )
