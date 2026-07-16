"""
policy.py — Hydra Brain v0.3.0
================================

Policy filter layer. Enforces operational eligibility rules before a model
reaches the scoring step in the routing pipeline.

The PolicyFilter reads a model's health block from the registry and applies
configurable exclusion rules. It is stateless and can be instantiated fresh
for each routing decision, or shared as a singleton.

Usage:
    from core.policy import PolicyFilter

    policy = PolicyFilter()
    eligible = policy.filter_candidates(models)
"""

import json
import os
from typing import Dict, Any, List, Optional

# Default policy settings (used when router_policy.json is missing or malformed)
_DEFAULT_POLICY = {
    "exclude_unhealthy_statuses": ["unavailable", "degraded", "rate_limited"],
    "exclude_open_circuit": True,
    "min_capability_score": 1,
}

POLICY_CONFIG_PATH = os.path.join("config", "router_policy.json")


def _load_policy_config() -> Dict[str, Any]:
    """Loads policy settings from router_policy.json, falling back to defaults."""
    if not os.path.exists(POLICY_CONFIG_PATH):
        return _DEFAULT_POLICY.copy()
    try:
        with open(POLICY_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("policy", _DEFAULT_POLICY.copy())
    except Exception:
        return _DEFAULT_POLICY.copy()


class PolicyFilter:
    """
    Enforces availability and quality gates on registry models.

    Eligibility rules applied in order:
    1. circuit != "open"  (circuit breaker gate)
    2. health.status not in excluded statuses
    3. (Optional) at least one capability score > 0
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """
        Args:
            config: Optional explicit policy config dict. If None, loads from
                    config/router_policy.json or falls back to defaults.
        """
        if config is not None:
            self._config = config
        else:
            self._config = _load_policy_config()

    @property
    def excluded_statuses(self) -> List[str]:
        """Returns the set of health statuses that disqualify a model."""
        raw = self._config.get("exclude_unhealthy_statuses", [])
        return [s.lower() for s in raw]

    @property
    def exclude_open_circuit(self) -> bool:
        """Returns whether models with an open circuit breaker are excluded."""
        return bool(self._config.get("exclude_open_circuit", True))

    @property
    def min_capability_score(self) -> int:
        """Returns the minimum aggregate capability score required for eligibility."""
        return int(self._config.get("min_capability_score", 1))

    def is_eligible(self, model: Dict[str, Any]) -> bool:
        """
        Evaluates whether a single model passes all policy gates.

        Args:
            model: A model dict from the registry (must include a 'health' block).

        Returns:
            True if the model is eligible for routing, False otherwise.
        """
        health = model.get("health") or {}
        status = (health.get("status") or "unknown").lower()
        circuit = (health.get("circuit") or "closed").lower()

        # Gate 1: Circuit breaker
        if self.exclude_open_circuit and circuit == "open":
            return False

        # Gate 2: Health status exclusion
        if status in self.excluded_statuses:
            return False

        # Gate 3: Minimum capability score (at least one capability must be non-zero)
        if self.min_capability_score > 0:
            caps = model.get("capabilities") or {}
            total_score = sum(v for v in caps.values() if isinstance(v, (int, float)))
            if total_score < self.min_capability_score:
                return False

        return True

    def filter_candidates(self, models: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Applies is_eligible() to a list of models, returning only those that pass.

        Args:
            models: List of model dicts from the registry.

        Returns:
            Filtered list of eligible model dicts.
        """
        return [m for m in models if self.is_eligible(m)]

    def explain(self, model: Dict[str, Any]) -> str:
        """
        Returns a human-readable explanation of why a model is eligible or not.
        Useful for debugging routing decisions.
        """
        health = model.get("health") or {}
        status = (health.get("status") or "unknown").lower()
        circuit = (health.get("circuit") or "closed").lower()
        model_id = model.get("model_id", "unknown")

        if self.exclude_open_circuit and circuit == "open":
            return f"{model_id}: EXCLUDED (circuit open)"

        if status in self.excluded_statuses:
            return f"{model_id}: EXCLUDED (status: {status})"

        if self.min_capability_score > 0:
            caps = model.get("capabilities") or {}
            total_score = sum(v for v in caps.values() if isinstance(v, (int, float)))
            if total_score < self.min_capability_score:
                return f"{model_id}: EXCLUDED (capability score {total_score} < {self.min_capability_score})"

        return f"{model_id}: ELIGIBLE (status: {status}, circuit: {circuit})"
