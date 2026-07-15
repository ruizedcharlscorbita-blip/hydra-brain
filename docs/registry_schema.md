# Hydra Registry Schema Specification v1.0

This document defines the schema structure of the Hydra Free Model Registry, located at `registry/free_models.json`.

---

## 1. Registry Envelope Schema

The root of the registry file is a versioned JSON envelope containing metadata and a list of discovered models.

### Properties

| Field | Type | Description |
| :--- | :--- | :--- |
| `schema_version` | `integer` | The schema specification version. For this specification, it is `1`. |
| `generated_at` | `string (ISO-8601)` | Timestamp when the registry file was serialized. |
| `provider` | `string` | The aggregate provider source name. E.g., `OpenRouter`. |
| `api_retrieved_at` | `string (ISO-8601)` | Timestamp when the models list was fetched from the upstream endpoint. |
| `hydra_synced_at` | `string (ISO-8601)` | Timestamp when the sync operation was run. |
| `statistics` | `object` | An object containing aggregated details of the models present in the registry. |
| `models` | `array` | List of normalized model objects. |

### Envelope Statistics Properties

| Field | Type | Description |
| :--- | :--- | :--- |
| `providers_count` | `integer` | Total number of distinct model providers. |
| `models_count` | `integer` | Total number of free models in the registry. |
| `average_context_length` | `integer` | Average context length (in tokens) across all models. |
| `largest_context_window` | `integer` | Maximum context length present in the registry. |
| `longest_provider` | `string` | The provider that offers the largest number of free models. |
| `latest_release` | `string` | The name and release date of the newest model in the registry. |
| `oldest_release` | `string` | The name and release date of the oldest model in the registry. |

---

## 2. Model Object Schema

Each entry in the `models` list is a normalized JSON object representing a specific free AI model.

### Primary Fields

| Field | Type | Description |
| :--- | :--- | :--- |
| `hydra_id` | `string` | Stable, deterministic identifier for internal Hydra scheduling. Formatted as `hydra-or-[0-9a-f]{8}` (generated via SHA-256 hash of the model ID). |
| `id` | `string` | The provider-specific raw model identifier. E.g., `tencent/hy3:free`. |
| `model_id` | `string` | Identical to `id`, kept for backward compatibility. |
| `provider` | `string` | Cleaned model provider name. E.g., `Tencent`. |
| `display_name` | `string` | Cleaned display name without provider prefixes or free suffixes. E.g., `Hy3`. |
| `description` | `string` | Narrative explanation of the model's target use cases and architecture. |
| `context_length` | `integer` | The maximum context size (in tokens) supported by the model. |
| `free` | `boolean` | Flag indicating whether the model is free of charge. Always `true`. |
| `release_date` | `string` | Formatted release date as `YYYY-MM-DD`, or `N/A`. |
| `updated_at` | `string (ISO-8601)` | Timestamp when the model record was updated in the registry. |
| `source` | `string` | Source catalog origin. E.g., `openrouter`. |

### Technical Metadata Fields

| Field | Type | Description |
| :--- | :--- | :--- |
| `architecture` | `object` | Dictionary containing technical attributes like tokenizer and modality. |
| `modalities` | `array of strings` | Modality inputs supported by the model. E.g., `["text"]`, `["text", "image"]`. |
| `supported_parameters` | `array of strings` | Parameter arguments supported by the endpoint. E.g., `["temperature", "top_p"]`. |
| `pricing` | `object` | Raw pricing details mapping prompt, completion, image, and request costs. |
| `input_cost` | `number` | cost per prompt token (should be `0.0` for free models). |
| `output_cost` | `number` | cost per completion token (should be `0.0` for free models). |
| `created` | `integer` | Unix timestamp of when the model was registered upstream. |
| `top_provider` | `object` | Details about the top execution provider hosted on the marketplace. |

---

## 3. Capabilities Schema (Placeholder)

Future-proof block for task capability tagging, currently initialized to `null`.

```json
"capabilities": {
    "coding": null,
    "reasoning": null,
    "vision": null,
    "tool_calling": null,
    "json_output": null,
    "streaming": null
}
```

---

## 4. Health Schema (Placeholder)

Future-proof block for latency and status tracking, currently initialized to `"unknown"` and `null`.

```json
"health": {
    "status": "unknown",
    "latency_ms": null,
    "success_rate": null,
    "last_checked": null
}
```

---

## 5. Sample Registry JSON Structure

```json
{
  "schema_version": 1,
  "generated_at": "2026-07-15T23:09:52.952203",
  "provider": "OpenRouter",
  "api_retrieved_at": "2026-07-15T23:09:52.952203",
  "hydra_synced_at": "2026-07-15T23:09:52.952203",
  "statistics": {
    "providers_count": 11,
    "models_count": 23,
    "average_context_length": 375115,
    "largest_context_window": 1048576,
    "longest_provider": "Nvidia",
    "latest_release": "Tencent Hy3 (2026-07-06)",
    "oldest_release": "Nousresearch Hermes 3 405B Instruct (2024-08-16)"
  },
  "models": [
    {
      "hydra_id": "hydra-or-a1b2c3d4",
      "id": "tencent/hy3:free",
      "model_id": "tencent/hy3:free",
      "provider": "Tencent",
      "display_name": "Hy3",
      "description": "A free Hunyuan model from Tencent.",
      "context_length": 262144,
      "architecture": {
        "modality": "text",
        "tokenizer": "Hunyuan"
      },
      "modalities": [
        "text"
      ],
      "pricing": {
        "prompt": "0",
        "completion": "0"
      },
      "input_cost": 0.0,
      "output_cost": 0.0,
      "supported_parameters": [
        "temperature"
      ],
      "created": 1735689600,
      "top_provider": {
        "context_length": 262144
      },
      "release_date": "2026-07-06",
      "updated_at": "2026-07-15T23:09:52.952203",
      "source": "openrouter",
      "free": true,
      "capabilities": {
        "coding": null,
        "reasoning": null,
        "vision": null,
        "tool_calling": null,
        "json_output": null,
        "streaming": null
      },
      "health": {
        "status": "unknown",
        "latency_ms": null,
        "success_rate": null,
        "last_checked": null
      }
    }
  ]
}
```
