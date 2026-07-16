"""
routing_engine.py — Hydra Brain v0.6.0
=======================================

Routing engine mapped to the HydraContext runtime structure.
Enforces policy exclusions and ranks candidate models using capability weights.
"""

import json
import logging
import os
from typing import Dict, List, Any, Optional, Tuple

from core.context.hydra_context import HydraContext
from core.engines.base import BaseEngine
from core.policies.policy import PolicyFilter
import registry.capability_registry as cap_reg

logger = logging.getLogger("hydra")

_DEFAULT_WEIGHTS = {
    "capability": 0.50,
    "latency": 0.25,
    "reliability": 0.25,
}

_DEFAULT_CONFIDENCE_MULTIPLIERS = {
    "high": 1.00,
    "medium": 0.90,
    "low": 0.75,
    "none": 0.50,
}

_DEFAULT_LATENCY_MAX_MS = 2000
_DEFAULT_NEUTRAL_RELIABILITY = 0.5
_DEFAULT_NEUTRAL_LATENCY_SCORE = 0.5

POLICY_CONFIG_PATH = os.path.join("config", "router_policy.json")


def _load_router_config() -> Dict[str, Any]:
    if not os.path.exists(POLICY_CONFIG_PATH):
        return {}
    try:
        with open(POLICY_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


class CapabilityRouter:
    """
    Scores and ranks registry models by a composite metric.
    """

    def __init__(self) -> None:
        cfg = _load_router_config()
        w = cfg.get("weights", _DEFAULT_WEIGHTS)
        self._w_cap = float(w.get("capability", _DEFAULT_WEIGHTS["capability"]))
        self._w_lat = float(w.get("latency", _DEFAULT_WEIGHTS["latency"]))
        self._w_rel = float(w.get("reliability", _DEFAULT_WEIGHTS["reliability"]))

        cm = cfg.get("confidence_multipliers", _DEFAULT_CONFIDENCE_MULTIPLIERS)
        self._confidence_multipliers: Dict[str, float] = {
            "high": float(cm.get("high", 1.00)),
            "medium": float(cm.get("medium", 0.90)),
            "low": float(cm.get("low", 0.75)),
            "none": float(cm.get("none", 0.50)),
        }

        lat_cfg = cfg.get("latency", {})
        self._lat_max_ms = float(lat_cfg.get("max_penalty_ms", _DEFAULT_LATENCY_MAX_MS))

        rel_cfg = cfg.get("reliability", {})
        self._neutral_reliability = float(
            rel_cfg.get("unknown_success_rate", _DEFAULT_NEUTRAL_RELIABILITY)
        )
        self._neutral_latency_score = _DEFAULT_NEUTRAL_LATENCY_SCORE

    def _score_capability(
        self,
        model: Dict[str, Any],
        intent_weights: Dict[str, float],
    ) -> float:
        active = {k: v for k, v in intent_weights.items() if v > 0.0}
        if not active:
            return 0.0

        max_possible = sum(w * 5 for w in active.values())
        if max_possible == 0:
            return 0.0

        caps = model.get("capabilities") or {}
        raw = sum(
            w * (caps.get(cap, 0) or 0)
            for cap, w in active.items()
        )
        s_cap = raw / max_possible

        confidence = model.get("capability_confidence", "none")
        multiplier = self._confidence_multipliers.get(confidence, 0.50)
        return s_cap * multiplier

    def _score_latency(self, model: Dict[str, Any]) -> float:
        health = model.get("health") or {}
        latency_ms = health.get("latency_ms")
        if latency_ms is None:
            return self._neutral_latency_score
        return 1.0 - min(1.0, float(latency_ms) / self._lat_max_ms)

    def _score_reliability(self, model: Dict[str, Any]) -> float:
        health = model.get("health") or {}
        rate = health.get("success_rate")
        if rate is None:
            return self._neutral_reliability
        return float(max(0.0, min(1.0, rate)))

    def score_model(
        self,
        model: Dict[str, Any],
        intent_weights: Dict[str, float],
    ) -> float:
        s_cap = self._score_capability(model, intent_weights)
        s_lat = self._score_latency(model)
        s_rel = self._score_reliability(model)
        return (self._w_cap * s_cap) + (self._w_lat * s_lat) + (self._w_rel * s_rel)

    def rank_models(
        self,
        models: List[Dict[str, Any]],
        intent_weights: Dict[str, float],
        policy: Optional[Any] = None,
    ) -> List[Tuple[float, Dict[str, Any]]]:
        candidates = models
        if policy is not None:
            candidates = policy.filter_candidates(models)

        scored = [
            (self.score_model(m, intent_weights), m)
            for m in candidates
        ]
        scored.sort(key=lambda x: x[0], reverse=True)

        if scored:
            top = scored[0]
            logger.info(
                f"CapabilityRouter ranked {len(scored)} candidates. "
                f"Top: {top[1].get('model_id')} (score={top[0]:.4f})"
            )
        else:
            logger.warning("CapabilityRouter: no eligible candidates after policy filter.")

        return scored

    def select_best(
        self,
        models: List[Dict[str, Any]],
        intent_weights: Dict[str, float],
        policy: Optional[Any] = None,
    ) -> Optional[Dict[str, Any]]:
        ranked = self.rank_models(models, intent_weights, policy)
        if not ranked:
            return None
        return ranked[0][1]

class RoutingEngine(BaseEngine):
    """
    Orchestrates candidate filtering and ranking using CapabilityRouter.
    Updates context.routing in-place.
    """

    def __init__(self) -> None:
        self.policy = PolicyFilter()
        self.router = CapabilityRouter()

    def process(self, context: HydraContext) -> None:
        all_models = cap_reg.get_all_models()
        if not all_models:
            raise RuntimeError("RoutingEngine: capability registry is empty.")

        eligible = self.policy.filter_candidates(all_models)
        if not eligible:
            raise RuntimeError("RoutingEngine: no eligible models after policy filter.")

        intent_weights = context.routing.intent_weights
        ranked = self.router.rank_models(eligible, intent_weights)
        if not ranked:
            raise RuntimeError("RoutingEngine: ranking produced no results.")

        context.routing.eligible_models = [m.get("model_id", "unknown") for m in eligible]
        context.routing.ranked_models = ranked
