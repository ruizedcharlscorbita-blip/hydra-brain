"""
capability_registry.py — Hydra Brain v0.3.0
=============================================

Read-only query API over the enriched free_models.json registry.

This module is the canonical interface for asking capability-based questions
about the model fleet. It is consumed by the routing layer (CapabilityRouter)
and can be used directly for diagnostics, reporting, or future orchestration.

All functions are stateless and load the registry on demand. No writes.

Usage:
    from registry.capability_registry import get_top_models, get_best_for_intent

    top_coders = get_top_models("coding", n=5)
    best = get_best_for_intent({"coding": 0.9, "reasoning": 0.4}, top_n=3)
"""

import json
import os
from typing import Dict, List, Optional, Any, Tuple

REGISTRY_PATH = os.path.join("registry", "free_models.json")

# Valid capability dimensions (must match registry schema)
CAPABILITY_KEYS = [
    "coding",
    "reasoning",
    "writing",
    "analysis",
    "vision",
    "chat",
    "tool_calling",
    "json_output",
    "streaming",
]

CONFIDENCE_LEVELS = ("high", "medium", "low", "none")


# ---------------------------------------------------------------------------
# Registry loader
# ---------------------------------------------------------------------------

def _load_models() -> List[Dict[str, Any]]:
    """Loads and returns the models list from the registry file."""
    if not os.path.exists(REGISTRY_PATH):
        return []
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "models" in data:
            return data["models"]
        elif isinstance(data, list):
            return data
        return []
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Core query functions
# ---------------------------------------------------------------------------

def get_all_models() -> List[Dict[str, Any]]:
    """Returns every model in the registry."""
    return _load_models()


def get_model_by_id(model_id_or_hydra_id: str) -> Optional[Dict[str, Any]]:
    """
    Finds a model by its provider model_id or stable hydra_id.
    Returns None if not found.
    """
    target = (model_id_or_hydra_id or "").strip()
    for m in _load_models():
        if m.get("model_id") == target or m.get("hydra_id") == target:
            return m
    return None


def get_models_by_capability(
    capability: str,
    min_score: int = 1,
) -> List[Dict[str, Any]]:
    """
    Returns all models where the given capability score >= min_score.

    Args:
        capability: One of the CAPABILITY_KEYS (e.g., "coding").
        min_score: Minimum score threshold (0–5). Default 1 (any non-zero).

    Returns:
        List of matching model dicts, unsorted.
    """
    if capability not in CAPABILITY_KEYS:
        return []
    result = []
    for m in _load_models():
        score = m.get("capabilities", {}).get(capability, 0) or 0
        if score >= min_score:
            result.append(m)
    return result


def get_top_models(
    capability: str,
    n: int = 5,
    min_score: int = 1,
) -> List[Dict[str, Any]]:
    """
    Returns the top-n models ranked by their score in the given capability.

    Args:
        capability: Capability dimension to rank by.
        n: Maximum number of results to return.
        min_score: Minimum score threshold.

    Returns:
        Sorted list (highest score first), up to n entries.
    """
    candidates = get_models_by_capability(capability, min_score=min_score)
    ranked = sorted(
        candidates,
        key=lambda m: m.get("capabilities", {}).get(capability, 0) or 0,
        reverse=True,
    )
    return ranked[:n]


def get_models_by_confidence(confidence: str) -> List[Dict[str, Any]]:
    """
    Returns all models with the given capability_confidence level.

    Args:
        confidence: One of "high", "medium", "low", "none".

    Returns:
        List of matching models.
    """
    if confidence not in CONFIDENCE_LEVELS:
        return []
    return [
        m for m in _load_models()
        if m.get("capability_confidence") == confidence
    ]


def get_healthy_models(
    capability: Optional[str] = None,
    min_score: int = 1,
) -> List[Dict[str, Any]]:
    """
    Returns models that pass a basic health gate:
    - health.status not in ("unavailable", "degraded", "rate_limited")
    - circuit != "open"

    Optionally also filters by capability score.

    Args:
        capability: Optional capability to filter by.
        min_score: Minimum score for the capability filter.

    Returns:
        List of eligible healthy models.
    """
    _unhealthy = {"unavailable", "degraded", "rate_limited"}
    result = []
    for m in _load_models():
        health = m.get("health") or {}
        status = (health.get("status") or "unknown").lower()
        circuit = (health.get("circuit") or "closed").lower()

        if circuit == "open":
            continue
        if status in _unhealthy:
            continue

        if capability is not None:
            score = m.get("capabilities", {}).get(capability, 0) or 0
            if score < min_score:
                continue

        result.append(m)
    return result


def get_best_for_intent(
    intent_weights: Dict[str, float],
    top_n: int = 5,
    healthy_only: bool = False,
) -> List[Tuple[float, Dict[str, Any]]]:
    """
    Given a set of capability weights from the IntentParser, ranks all models
    by weighted capability match score and returns the top-n results.

    The match score is:
        S_cap = Σ(intent_weight_c × model_cap_c) / Σ(intent_weight_c × 5)

    A confidence multiplier is applied to discount inferred scores:
        high → 1.00, medium → 0.90, low → 0.75, none → 0.50

    Args:
        intent_weights: Dict mapping capability names to float weights (0.0–1.0).
        top_n: Maximum number of results to return.
        healthy_only: If True, applies the health gate before ranking.

    Returns:
        List of (score, model_dict) tuples, sorted descending by score.
    """
    _confidence_multipliers = {
        "high": 1.00,
        "medium": 0.90,
        "low": 0.75,
        "none": 0.50,
    }

    # Filter to active intent dimensions only
    active = {k: v for k, v in intent_weights.items() if v > 0.0 and k in CAPABILITY_KEYS}
    if not active:
        return []

    max_possible = sum(w * 5 for w in active.values())
    if max_possible == 0:
        return []

    models = get_healthy_models() if healthy_only else _load_models()
    scored: List[Tuple[float, Dict[str, Any]]] = []

    for m in models:
        caps = m.get("capabilities") or {}
        raw_score = sum(
            w * (caps.get(cap, 0) or 0)
            for cap, w in active.items()
        )
        s_cap = raw_score / max_possible

        # Apply confidence multiplier
        confidence = m.get("capability_confidence", "none")
        multiplier = _confidence_multipliers.get(confidence, 0.50)
        final_score = s_cap * multiplier

        scored.append((final_score, m))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:top_n]


def search_models(query: str) -> List[Dict[str, Any]]:
    """
    Case-insensitive text search across provider, display_name, and model_id.

    Args:
        query: Search string.

    Returns:
        List of matching model dicts.
    """
    q = (query or "").strip().lower()
    if not q:
        return []
    result = []
    for m in _load_models():
        if (
            q in (m.get("provider") or "").lower()
            or q in (m.get("display_name") or "").lower()
            or q in (m.get("model_id") or "").lower()
        ):
            result.append(m)
    return result
