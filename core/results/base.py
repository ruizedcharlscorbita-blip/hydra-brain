"""
base.py — Hydra Brain v0.5.0
=============================

Common base class for all result objects in Hydra.
Provides unified structure for timestamping, metadata storage, and serialization.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict


def _utc_now() -> str:
    """Returns the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


@dataclass(kw_only=True)
class BaseResult:
    """
    Abstract base result class.
    
    All Hydra output envelopes inherit from this class to ensure consistent
    serialization, metadata tagging, and lifecycle tracking.
    """
    timestamp: str = field(default_factory=_utc_now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the result to a dictionary."""
        raise NotImplementedError("Subclasses must implement to_dict()")
