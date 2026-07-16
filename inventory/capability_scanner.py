"""
capability_scanner.py — Hydra Brain v0.3.0
============================================

Populates capability scores for each model in the registry using a 3-tier strategy:

  Tier 1 — Exact Match:   model_id found in capabilities/model_profiles.json > models
  Tier 2 — Family Match:  model family slug matches a key in > families
  Tier 3 — Signal Inference: no profile exists; infer from metadata signals (modalities,
                              supported_parameters, description keywords, context length)

Each model receives a `capability_confidence` field at the root level:
  "high"   — exact profile match
  "medium" — family match
  "low"    — inferred from signals
  "none"   — no signals found; all zeros retained

Can be run standalone:
  py inventory/capability_scanner.py
"""

import json
import os
import re
import sys
from typing import Dict, List, Any, Optional, Tuple

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROFILES_PATH = os.path.join("capabilities", "model_profiles.json")
REGISTRY_PATH = os.path.join("registry", "free_models.json")

# ---------------------------------------------------------------------------
# Capability dimensions (must match registry schema)
# ---------------------------------------------------------------------------

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

ZERO_CAPS: Dict[str, int] = {k: 0 for k in CAPABILITY_KEYS}


# ---------------------------------------------------------------------------
# Profile loader (cached)
# ---------------------------------------------------------------------------

_profiles_cache: Optional[Dict[str, Any]] = None


def _load_profiles() -> Dict[str, Any]:
    """Loads and caches model_profiles.json."""
    global _profiles_cache
    if _profiles_cache is not None:
        return _profiles_cache
    if not os.path.exists(PROFILES_PATH):
        _profiles_cache = {"families": {}, "models": {}}
        return _profiles_cache
    try:
        with open(PROFILES_PATH, "r", encoding="utf-8") as f:
            _profiles_cache = json.load(f)
    except Exception:
        _profiles_cache = {"families": {}, "models": {}}
    return _profiles_cache


def _scores_from_profile(profile: Dict[str, Any]) -> Dict[str, int]:
    """Extracts capability scores from a profile dict, ignoring metadata keys."""
    return {k: int(profile[k]) for k in CAPABILITY_KEYS if k in profile}


# ---------------------------------------------------------------------------
# Tier 1 — Exact model_id match
# ---------------------------------------------------------------------------

def _exact_match(model_id: str, profiles: Dict[str, Any]) -> Optional[Dict[str, int]]:
    """Returns scores if model_id is explicitly listed in profiles > models."""
    models_section = profiles.get("models", {})
    if model_id in models_section:
        return _scores_from_profile(models_section[model_id])
    return None


# ---------------------------------------------------------------------------
# Tier 2 — Family slug match
# ---------------------------------------------------------------------------

def _extract_family_slugs(model_id: str) -> List[str]:
    """
    Derives candidate family slugs from a model_id.

    Examples:
      google/gemma-4-26b-a4b-it:free  ->  ["gemma-4-26b-a4b-it", "gemma-4", "gemma"]
      qwen/qwen3-coder:free           ->  ["qwen3-coder", "qwen3"]
      nvidia/nemotron-nano-12b-v2-vl  ->  ["nemotron-nano-12b-v2-vl", "nemotron-nano", "nemotron"]
      meta-llama/llama-3.3-70b-instruct:free -> ["llama-3.3-70b-instruct", "llama-3.3", "llama"]
    """
    # Strip provider prefix (before /) and variant suffix (:free etc.)
    base = model_id
    if "/" in base:
        base = base.split("/", 1)[1]
    if ":" in base:
        base = base.split(":")[0]

    slugs = []
    # Start with the full base name, then progressively strip trailing segments
    current = base
    while current:
        slugs.append(current)
        # Remove last dash-separated token
        parts = current.rsplit("-", 1)
        if len(parts) == 1:
            break
        current = parts[0]

    return slugs


def _family_match(model_id: str, profiles: Dict[str, Any]) -> Optional[Tuple[str, Dict[str, int]]]:
    """
    Returns (matched_family_key, scores) if any family slug matches a key in profiles > families.
    Uses the most-specific (longest) matching family slug.
    """
    families = profiles.get("families", {})
    if not families:
        return None

    slugs = _extract_family_slugs(model_id)
    for slug in slugs:  # slugs are ordered most-specific to least-specific
        if slug in families:
            return slug, _scores_from_profile(families[slug])
    return None


# ---------------------------------------------------------------------------
# Tier 3 — Signal inference
# ---------------------------------------------------------------------------

def _infer_from_signals(model: Dict[str, Any]) -> Dict[str, int]:
    """
    Infers capability scores from available metadata signals when no profile exists.

    Signals used:
    - modalities: image/video input -> vision
    - supported_parameters: tools/tool_choice -> tool_calling
    - supported_parameters: response_format/structured_outputs -> json_output
    - supported_parameters: reasoning/include_reasoning -> reasoning boost
    - description keywords: code, reason, instruct, chat, analysis, write
    - context_length > 100K -> analysis boost
    """
    caps = dict(ZERO_CAPS)

    modalities = model.get("modalities", [])
    # Normalize to a flat string for easy checking
    modalities_str = " ".join(str(m).lower() for m in modalities)

    params = model.get("supported_parameters", [])
    params_set = set(p.lower() for p in params)

    description = (model.get("description") or "").lower()
    context_length = model.get("context_length", 0) or 0

    # ---- Vision ----
    if any(kw in modalities_str for kw in ("image", "video", "audio")):
        if "image" in modalities_str or "video" in modalities_str:
            caps["vision"] = 3

    # ---- Tool calling ----
    if "tools" in params_set or "tool_choice" in params_set:
        caps["tool_calling"] = 3

    # ---- JSON / structured output ----
    if "response_format" in params_set or "structured_outputs" in params_set:
        caps["json_output"] = 3

    # ---- Reasoning ----
    if "reasoning" in params_set or "include_reasoning" in params_set:
        caps["reasoning"] = 3
    if any(kw in description for kw in ("reason", "chain-of-thought", "think", "math")):
        caps["reasoning"] = max(caps["reasoning"], 3)

    # ---- Coding ----
    if any(kw in description for kw in ("code", "coding", "programming", "developer")):
        caps["coding"] = 3

    # ---- Chat (default baseline if it seems like an instruct/chat model) ----
    instruct_signals = (
        "instruct" in (model.get("model_id", "") or "").lower()
        or "chat" in (model.get("model_id", "") or "").lower()
        or "instruct" in description
        or "chat" in description
        or "conversation" in description
    )
    if instruct_signals:
        caps["chat"] = 3

    # ---- Writing ----
    if any(kw in description for kw in ("write", "writing", "story", "creative", "prose")):
        caps["writing"] = 3

    # ---- Analysis ----
    if any(kw in description for kw in ("analysis", "summariz", "extract", "document")):
        caps["analysis"] = 3
    if context_length >= 100000:
        caps["analysis"] = max(caps["analysis"], 3)

    # ---- Streaming: present for all normal text models ----
    # Only withhold if the model appears to be non-text (audio/image generation)
    is_generation_only = (
        "text" not in modalities_str and
        any(kw in modalities_str for kw in ("audio", "image"))
    )
    if not is_generation_only:
        caps["streaming"] = 4

    return caps


# ---------------------------------------------------------------------------
# Confidence determination helper
# ---------------------------------------------------------------------------

def _has_any_signal(caps: Dict[str, int]) -> bool:
    """Returns True if at least one capability score is non-zero."""
    return any(v > 0 for v in caps.values())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scan_model(model: Dict[str, Any]) -> Dict[str, Any]:
    """
    Scores a single model dict and returns a copy with populated
    `capabilities` and `capability_confidence` fields.

    Does NOT mutate the input dict.
    """
    profiles = _load_profiles()
    model_id = model.get("model_id") or model.get("id", "")

    result = dict(model)
    confidence = "none"
    scores: Dict[str, int] = {}

    # --- Tier 1: Exact match ---
    exact = _exact_match(model_id, profiles)
    if exact is not None:
        scores = exact
        confidence = "high"
    else:
        # --- Tier 2: Family match ---
        family_result = _family_match(model_id, profiles)
        if family_result is not None:
            _, scores = family_result
            confidence = "medium"
        else:
            # --- Tier 3: Signal inference ---
            inferred = _infer_from_signals(model)
            scores = inferred
            if _has_any_signal(scores):
                confidence = "low"
            else:
                confidence = "none"

    # Merge with existing capability keys — preserve any unrecognized keys
    existing_caps = model.get("capabilities", {})
    if not isinstance(existing_caps, dict):
        existing_caps = {}

    merged_caps = dict(ZERO_CAPS)  # start from zero baseline
    merged_caps.update(existing_caps)  # layer existing values
    merged_caps.update(scores)  # scanner scores take precedence

    # Clamp all values to 0-5 integer range
    for k in CAPABILITY_KEYS:
        merged_caps[k] = max(0, min(5, int(merged_caps.get(k, 0))))

    result["capabilities"] = merged_caps
    result["capability_confidence"] = confidence

    return result


def scan_all(models: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Scans an entire list of model dicts and returns a new list with
    populated capabilities and capability_confidence fields.
    """
    return [scan_model(m) for m in models]


def scan_registry() -> None:
    """
    Loads the registry from REGISTRY_PATH, runs the capability scanner
    over all models, and writes the updated registry back to disk.

    Preserves the envelope structure (schema_version, statistics, etc.).
    """
    if not os.path.exists(REGISTRY_PATH):
        print(f"[CapabilityScanner] Registry not found at: {REGISTRY_PATH}")
        return

    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[CapabilityScanner] Failed to load registry: {e}")
        return

    if isinstance(data, dict) and "models" in data:
        models = data["models"]
    elif isinstance(data, list):
        models = data
        data = {"models": models}
    else:
        print("[CapabilityScanner] Unrecognised registry format.")
        return

    updated_models = scan_all(models)

    # Tally confidence distribution for reporting
    tally: Dict[str, int] = {"high": 0, "medium": 0, "low": 0, "none": 0}
    for m in updated_models:
        conf = m.get("capability_confidence", "none")
        tally[conf] = tally.get(conf, 0) + 1

    if isinstance(data, dict):
        data["models"] = updated_models
    else:
        data = {"models": updated_models}

    try:
        with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[CapabilityScanner] Failed to write registry: {e}")
        return

    print(f"[CapabilityScanner] Scanned {len(updated_models)} models.")
    print(f"  Confidence: high={tally['high']}  medium={tally['medium']}  "
          f"low={tally['low']}  none={tally['none']}")


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 40)
    print("Hydra Capability Scanner")
    print("=" * 40)
    scan_registry()
    print("Done.")
