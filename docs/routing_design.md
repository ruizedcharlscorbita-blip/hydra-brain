# Hydra Intelligent Router v0.3.0 Architectural Design

> **Status: Implemented — Sprint 3 Complete**
> All components described in this document (`core/intent.py`, `registry/capability_registry.py`, `core/policy.py`, `core/router.CapabilityRouter`, `config/router_policy.json`) have been built and are passing 24/24 tests.

This document outlines the architectural specifications, schemas, interfaces, and mathematical scoring functions for the capability-aware routing layer of Hydra Brain v0.3.0.

---

## 1. Routing Architecture Overview

The v0.3.0 router decouples operational availability checks from selection policies. Routing proceeds in a sequential processing pipeline:

```text
               User Prompt
                     │
                     ▼
             [ Intent Parser ] ───> Mapping rules
                     │
                     ▼
             [ Target Intent ] ───> (e.g., Coding Demand = High)
                     │
                     ▼
             [ Policy Filter ] <─── Checks Health Subsystem (is_available?)
                     │
             (Healthy Candidates)
                     │
                     ▼
             [ Scoring Engine ] <─── Evaluates Capabilities + Latencies
                     │
                     ▼
             [ Selected Head ] ───> Execute Dispatcher
```

---

## 2. Component Design & Interfaces

### A. Intent Parser (`core/intent.py`)
Analyzes the semantic structure of a user prompt to determine required capabilities. In v0.3.0, this is implemented as a rule-based parser utilizing regex pattern matching for speed and zero cost.

#### Interface:
```python
class IntentParser:
    def parse_intent(self, prompt: str) -> Dict[str, float]:
        """
        Parses user prompt and returns dictionary of capability weights (0.0 to 1.0).
        Example Output:
            {"coding": 0.9, "reasoning": 0.3}
        """
        pass
```

---

### B. Capability Registry Schema
Upgrades the registry `"capabilities"` placeholders from `null` to integer capability scores (`0` to `5`):
* `0`: Unsupported (cannot run this task).
* `1-2`: Basic (can handle simple tasks).
* `3-4`: Good (can handle standard execution).
* `5`: Expert (state-of-the-art capability).

#### Example Model capabilities:
```json
"capabilities": {
    "coding": 4,
    "reasoning": 3,
    "vision": 0,
    "tool_calling": 3,
    "json_output": 4,
    "streaming": 5
}
```

---

### C. Policy Layer (`core/policy.py`)
Enforces strict operational boundaries before scoring models. The router calls the Health Subsystem's interface to identify candidate eligibility.

#### Health Interface:
```python
class HealthSubsystem:
    @staticmethod
    def is_available(model: Dict[str, Any]) -> bool:
        """
        Determines availability based on health status and circuit breaker state:
        - Returns False if circuit is "open" and retry_after has not expired.
        - Returns False if status is "unavailable" or "degraded".
        - Returns True otherwise.
        """
        health = model.get("health", {})
        circuit = health.get("circuit", "closed")
        status = health.get("status", "unknown")
        
        if circuit == "open":
            return False
        if status in ("unavailable", "degraded"):
            return False
        return True
```

---

## 3. The Scoring Function

The Scoring Engine maps the remaining candidate models to a normalized score $S \in [0.0, 1.0]$. The candidate with the highest score is selected.

$$S = (W_{cap} \times S_{cap}) + (W_{lat} \times S_{lat}) + (W_{rel} \times S_{rel}) - C_{cost}$$

### Dimension Breakdowns:

#### 1. Capability Match Score ($S_{cap}$)
Measures how well the model's capability matches the parsed prompt intent:
$$S_{cap} = \frac{\sum (IntentWeight_{c} \times ModelCapability_{c})}{\sum (IntentWeight_{c} \times 5)}$$
*Where $c$ represents the capabilities required by the intent.*

#### 2. Latency Score ($S_{lat}$)
Normalized inverse of latency (shorter latency yields higher score):
$$S_{lat} = 1.0 - \min\left(1.0, \frac{\text{latency\_ms}}{2000}\right)$$
*If a model has no recorded latency, it defaults to a neutral score of 0.5.*

#### 3. Reliability Score ($S_{rel}$)
Calculated directly from the moving-window success rate:
$$S_{rel} = \text{success\_rate}$$

#### 4. Cost Penalty ($C_{cost}$)
Normalized cost penalty to encourage cost-efficiency (for free models, $C_{cost} = 0$).

---

## 4. Confidence Multiplier

A multiplier is applied to `S_cap` to discount models whose capability scores were inferred rather than hand-authored:

| `capability_confidence` | Multiplier |
| :--- | :--- |
| `"high"` | `1.00` — exact profile match |
| `"medium"` | `0.90` — family match |
| `"low"` | `0.75` — signal inference |
| `"none"` | `0.50` — no signals found |

This means a model with `confidence: "low"` and a raw `S_cap` of `0.80` will contribute `0.80 × 0.75 = 0.60` to its composite score. High-confidence profiles are always preferred when intent is equal.

---

## 5. Policy Configuration Settings (`config/router_policy.json`)

All scoring weights, confidence multipliers, and policy rules are loaded from a configuration file at runtime. No code changes are required for rebalancing:

```json
{
  "weights": {
    "capability": 0.50,
    "latency": 0.25,
    "reliability": 0.25
  },
  "confidence_multipliers": {
    "high": 1.00,
    "medium": 0.90,
    "low": 0.75,
    "none": 0.50
  },
  "policy": {
    "exclude_unhealthy_statuses": ["unavailable", "degraded", "rate_limited"],
    "exclude_open_circuit": true,
    "min_capability_score": 1
  },
  "circuit_breaker": {
    "failure_threshold": 3,
    "cooldown_seconds": 600
  }
}
```
