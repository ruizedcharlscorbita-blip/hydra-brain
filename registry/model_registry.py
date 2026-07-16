import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from providers.openrouter.discovery import OpenRouterDiscovery

REGISTRY_PATH = os.path.join("registry", "free_models.json")

def load_registry() -> List[Dict[str, Any]]:
    """Loads the model registry from free_models.json (supporting list or envelope structure)."""
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

def save_registry(models: List[Dict[str, Any]]) -> None:
    """Saves the given model list wrapped in a schema envelope to free_models.json."""
    dir_name = os.path.dirname(REGISTRY_PATH)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
        
    # Self-healing schema normalization
    import hashlib
    for model in models:
        model_id = model.get("model_id")
        if not model.get("hydra_id") and model_id:
            h = hashlib.sha256(model_id.encode("utf-8")).hexdigest()[:8]
            model["hydra_id"] = f"hydra-or-{h}"
            
        caps = model.get("capabilities", {})
        if not isinstance(caps, dict):
            caps = {}
        model["capabilities"] = {
            "coding": caps.get("coding") if isinstance(caps.get("coding"), int) else 0,
            "reasoning": caps.get("reasoning") if isinstance(caps.get("reasoning"), int) else 0,
            "writing": caps.get("writing") if isinstance(caps.get("writing"), int) else 0,
            "analysis": caps.get("analysis") if isinstance(caps.get("analysis"), int) else 0,
            "vision": caps.get("vision") if isinstance(caps.get("vision"), int) else 0,
            "chat": caps.get("chat") if isinstance(caps.get("chat"), int) else 0,
            "tool_calling": caps.get("tool_calling") if isinstance(caps.get("tool_calling"), int) else 0,
            "json_output": caps.get("json_output") if isinstance(caps.get("json_output"), int) else 0,
            "streaming": caps.get("streaming") if isinstance(caps.get("streaming"), int) else 0
        }
        if "health" not in model:
            model["health"] = {
                "status": "unknown",
                "latency_ms": None,
                "success_rate": 0.0,
                "last_checked": None,
                "consecutive_successes": 0,
                "consecutive_failures": 0,
                "history": [],
                "average_tokens_per_second": None,
                "last_error": None,
                "circuit": "closed",
                "opened_at": None,
                "retry_after": None
            }
        if "capability_confidence" not in model:
            model["capability_confidence"] = "none"
            
        if "free" not in model:
            model["free"] = True
            
        if "description" not in model:
            model["description"] = "No description available."
        if "architecture" not in model:
            model["architecture"] = {}
        if "modalities" not in model:
            model["modalities"] = ["text"]
        if "pricing" not in model:
            model["pricing"] = {"prompt": "0", "completion": "0"}
        
    envelope = {
        "schema_version": 1,
        "generated_at": datetime.now().isoformat(),
        "provider": "OpenRouter",
        "models": models
    }
        
    try:
        with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump(envelope, f, indent=2)
    except Exception as e:
        raise RuntimeError(f"Failed to write model registry: {e}")

# --- New Registry API v1.0 ---

def get_all() -> List[Dict[str, Any]]:
    """Returns all models present in the registry."""
    return load_registry()

def get_free() -> List[Dict[str, Any]]:
    """Returns all models that are free (free is True)."""
    return [m for m in load_registry() if m.get("free") is True]

def get_provider(provider_name: str) -> List[Dict[str, Any]]:
    """Returns all models belonging to a specific provider (case-insensitive)."""
    prov_lower = provider_name.strip().lower()
    return [m for m in load_registry() if m.get("provider", "").lower() == prov_lower]

def get_model(model_id_or_hydra_id: str) -> Optional[Dict[str, Any]]:
    """Finds a model by its provider model ID or stable Hydra ID."""
    target = model_id_or_hydra_id.strip()
    for m in load_registry():
        if m.get("model_id") == target or m.get("hydra_id") == target:
            return m
    return None

def search(query: str) -> List[Dict[str, Any]]:
    """Searches models matching query in provider, display name, or model ID (case-insensitive)."""
    q = query.strip().lower()
    if not q:
        return []
    results = []
    for m in load_registry():
        provider = m.get("provider", "").lower()
        display_name = m.get("display_name", "").lower()
        model_id = m.get("model_id", "").lower()
        if q in provider or q in display_name or q in model_id:
            results.append(m)
    return results

# --- Backward Compatibility APIs ---

def get_free_models() -> List[Dict[str, Any]]:
    """Backward-compatible wrapper for get_free()."""
    return get_free()

def find_model(model_id: str) -> Optional[Dict[str, Any]]:
    """Backward-compatible wrapper for get_model()."""
    return get_model(model_id)

def refresh_registry() -> List[Dict[str, Any]]:
    """Triggers OpenRouter model discovery and updates the local registry."""
    discovery = OpenRouterDiscovery()
    models = discovery.discover_models()
    save_registry(models)
    return models
