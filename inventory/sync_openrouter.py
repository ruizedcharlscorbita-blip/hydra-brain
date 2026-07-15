import os
import sys
import json
import csv
import hashlib
import urllib.request
from datetime import datetime
from typing import List, Dict, Any

# Ensure stdout uses UTF-8 to prevent encoding crashes on Windows console hosts
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

REGISTRY_DIR = "registry"

def load_dotenv() -> None:
    """Parses .env file manually to load environment configurations without overriding preset keys."""
    env_path = ".env"
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip()
                        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                            val = val[1:-1]
                        if key not in os.environ:
                            os.environ[key] = val
        except Exception:
            pass

def generate_stable_id(model_id: str) -> str:
    """Generates a stable, deterministic hex ID from the model ID using SHA-256."""
    h = hashlib.sha256(model_id.encode("utf-8")).hexdigest()[:8]
    return f"hydra-or-{h}"

def format_context(length: int) -> str:
    """Formats context length into K (thousands) or M (millions) display string."""
    if length is None:
        return "N/A"
    if length >= 1000000:
        if length % 1048576 == 0:
            return f"{length // 1048576}M"
        return f"{length // 1000}K"
    return f"{length // 1000}K"

def load_existing_models(file_path: str) -> List[Dict[str, Any]]:
    """Loads models list supporting list or envelope structures from an existing registry file."""
    if not os.path.exists(file_path):
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict) and "models" in data:
                return data["models"]
            elif isinstance(data, list):
                return data
            return []
    except Exception:
        return []

def get_mock_models(version: str) -> List[Dict[str, Any]]:
    """Returns mock raw models list matching OpenRouter API structure for testing."""
    if version == "2":
        return [
            {
                "id": "cohere/north-mini-code:free",
                "name": "Cohere: North Mini Code (free)",
                "description": "A free code generation model from Cohere.",
                "context_length": 256000,
                "architecture": {"modality": "text", "tokenizer": "Cohere"},
                "pricing": {"prompt": "0", "completion": "0"},
                "created": 1735689600,
                "supported_parameters": ["temperature", "max_tokens"],
                "top_provider": {"context_length": 256000}
            },
            {
                "id": "google/gemini-flash:free",
                "name": "Google: Gemini Flash (free)",
                "description": "Google lightweight multi-modal model.",
                "context_length": 256000,  # Context updated: 128K -> 256K
                "architecture": {"modality": "text+image", "tokenizer": "Gemini"},
                "pricing": {"prompt": "0", "completion": "0"},
                "created": 1735689600,
                "supported_parameters": ["temperature", "top_p"],
                "top_provider": {"context_length": 256000}
            },
            {
                "id": "qwen/3:free",
                "name": "Qwen: Qwen 3 (free)",
                "description": "A free Qwen reasoning model.",
                "context_length": 32000,
                "architecture": {"modality": "text", "tokenizer": "Qwen"},
                "pricing": {"prompt": "0", "completion": "0"},
                "created": 1735689600,
                "supported_parameters": ["temperature"],
                "top_provider": {"context_length": 32000}
            },
            {
                "id": "tencent/hy3:free",
                "name": "Tencent: Hy3 (free)",  # Added model
                "description": "A free Hunyuan model from Tencent.",
                "context_length": 262144,
                "architecture": {"modality": "text", "tokenizer": "Hunyuan"},
                "pricing": {"prompt": "0", "completion": "0"},
                "created": 1735689600,
                "supported_parameters": ["temperature"],
                "top_provider": {"context_length": 262144}
            },
            {
                "id": "poolside/laguna-xs:free",
                "name": "Poolside: Laguna XS (free)",  # Added model
                "description": "A free software development model.",
                "context_length": 262144,
                "architecture": {"modality": "text", "tokenizer": "Poolside"},
                "pricing": {"prompt": "0", "completion": "0"},
                "created": 1735689600,
                "supported_parameters": ["temperature"],
                "top_provider": {"context_length": 262144}
            }
        ]
    else:
        # Version 1
        return [
            {
                "id": "cohere/north-mini-code:free",
                "name": "Cohere: North Mini Code (free)",
                "description": "A free code generation model from Cohere.",
                "context_length": 256000,
                "architecture": {"modality": "text", "tokenizer": "Cohere"},
                "pricing": {"prompt": "0", "completion": "0"},
                "created": 1735689600,
                "supported_parameters": ["temperature", "max_tokens"],
                "top_provider": {"context_length": 256000}
            },
            {
                "id": "google/gemini-flash:free",
                "name": "Google: Gemini Flash (free)",
                "description": "Google lightweight multi-modal model.",
                "context_length": 128000,
                "architecture": {"modality": "text+image", "tokenizer": "Gemini"},
                "pricing": {"prompt": "0", "completion": "0"},
                "created": 1735689600,
                "supported_parameters": ["temperature", "top_p"],
                "top_provider": {"context_length": 128000}
            },
            {
                "id": "deepseek/lite:free",
                "name": "Deepseek: DeepSeek Lite (free)",  # Will be removed in v2
                "description": "A free lightweight DeepSeek model.",
                "context_length": 64000,
                "architecture": {"modality": "text", "tokenizer": "DeepSeek"},
                "pricing": {"prompt": "0", "completion": "0"},
                "created": 1735689600,
                "supported_parameters": ["temperature"],
                "top_provider": {"context_length": 64000}
            },
            {
                "id": "qwen/3:free",
                "name": "Qwen: Qwen 3 (free)",
                "description": "A free Qwen reasoning model.",
                "context_length": 32000,
                "architecture": {"modality": "text", "tokenizer": "Qwen"},
                "pricing": {"prompt": "0", "completion": "0"},
                "created": 1735689600,
                "supported_parameters": ["temperature"],
                "top_provider": {"context_length": 32000}
            }
        ]

def run_sync() -> None:
    print("========================================")
    print("Hydra Inventory Synchronizer")
    print("========================================\n")
    
    load_dotenv()
    
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    mock_mode = os.getenv("HYDRA_MOCK", "").lower() == "true" or not api_key or api_key.startswith("mock")
    
    print("Connecting to OpenRouter...\n")
    
    api_retrieved_at = datetime.now().isoformat()
    raw_response = {}
    if mock_mode:
        mock_version = os.getenv("MOCK_INVENTORY_VERSION", "1")
        mock_data = get_mock_models(mock_version)
        raw_response = {"data": mock_data}
        total_discovered = 342
    else:
        url = "https://openrouter.ai/api/v1/models"
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                raw_response = json.loads(response.read().decode("utf-8"))
                total_discovered = len(raw_response.get("data", []))
        except Exception as e:
            print(f"Error connecting to OpenRouter: {e}")
            sys.exit(1)
            
    print(f"{total_discovered} models discovered\n")
    print("Filtering free models...\n")
    
    raw_models = raw_response.get("data", [])
    free_models_temp = []
    
    for item in raw_models:
        model_id = item.get("id", "")
        name = item.get("name", "")
        pricing = item.get("pricing", {})
        
        prompt_cost = 0.0
        output_cost = 0.0
        try:
            prompt_cost = float(pricing.get("prompt", 0.0))
            output_cost = float(pricing.get("completion", 0.0))
        except (ValueError, TypeError):
            pass
            
        # Pricing is the primary check, naming is fallback
        is_free = False
        if prompt_cost == 0.0 and output_cost == 0.0:
            is_free = True
        elif "(free)" in name.lower() or model_id.endswith(":free"):
            is_free = True
            
        if is_free:
            # Resolve provider name
            provider = ""
            if "/" in model_id:
                provider = model_id.split("/")[0].title()
            elif ":" in name:
                provider = name.split(":")[0].strip()
            else:
                provider = "OpenRouter"
                
            # Resolve display name
            display_name = name
            if ":" in name:
                display_name = name.split(":", 1)[1].strip()
            display_name = display_name.replace("(free)", "").replace("(Free)", "").strip()
            
            # Resolve release date
            created_timestamp = item.get("created")
            release_date = "N/A"
            if created_timestamp:
                try:
                    release_date = datetime.fromtimestamp(created_timestamp).strftime("%Y-%m-%d")
                except Exception:
                    pass
                    
            # Extract additional fields
            description = item.get("description", "No description available.")
            architecture = item.get("architecture", {})
            
            # Modalities check
            modalities = architecture.get("modality", [])
            if isinstance(modalities, str):
                modalities = [modalities]
            elif not modalities:
                modalities = ["text"]
                
            supported_parameters = item.get("supported_parameters", ["temperature", "top_p"])
            top_provider = item.get("top_provider", {})
            
            # Generate deterministic stable Hydra ID
            hydra_id = generate_stable_id(model_id)
            
            # Capabilities Placeholder
            capabilities = {
                "coding": None,
                "reasoning": None,
                "vision": None,
                "tool_calling": None,
                "json_output": None,
                "streaming": None
            }
            
            # Health Placeholder
            health = {
                "status": "unknown",
                "latency_ms": None,
                "success_rate": None,
                "last_checked": None
            }
            
            free_models_temp.append({
                "hydra_id": hydra_id,
                "id": model_id,
                "model_id": model_id,
                "provider": provider,
                "display_name": display_name,
                "description": description,
                "context_length": item.get("context_length", 0),
                "architecture": architecture,
                "modalities": modalities,
                "pricing": pricing,
                "input_cost": prompt_cost,
                "output_cost": output_cost,
                "supported_parameters": supported_parameters,
                "created": created_timestamp,
                "top_provider": top_provider,
                "release_date": release_date,
                "api_retrieved_at": api_retrieved_at,
                "hydra_synced_at": datetime.now().isoformat(),
                "source": "openrouter",
                "free": True,
                "capabilities": capabilities,
                "health": health
            })
            
    # Sort free models alphabetically by ID
    free_models_temp = sorted(free_models_temp, key=lambda x: x["model_id"])
    
    print(f"{len(free_models_temp)} free models identified\n")
    print("Writing registry...\n")
    
    # Load old registry to compute diffs
    models_path = os.path.join(REGISTRY_DIR, "free_models.json")
    old_models = load_existing_models(models_path)
    
    # Ensure directories exist
    os.makedirs(REGISTRY_DIR, exist_ok=True)
    os.makedirs(os.path.join(REGISTRY_DIR, "history"), exist_ok=True)
    os.makedirs("reports", exist_ok=True)
    
    # Calculate stats for registry metadata
    prov_counts = {}
    total_context = 0
    longest_context = -1
    longest_model_name = ""
    newest_model_name = ""
    newest_time = -1
    newest_date = "N/A"
    oldest_model_name = ""
    oldest_time = float("inf")
    oldest_date = "N/A"
    
    for model in free_models_temp:
        prov = model["provider"]
        prov_counts[prov] = prov_counts.get(prov, 0) + 1
        
        ctx = model["context_length"]
        total_context += ctx
        if ctx > longest_context:
            longest_context = ctx
            longest_model_name = f"{model['provider']} {model['display_name']}"
            
        created_time = model.get("created")
        if created_time:
            if created_time > newest_time:
                newest_time = created_time
                newest_model_name = f"{model['provider']} {model['display_name']}"
                newest_date = model["release_date"]
            if created_time < oldest_time:
                oldest_time = created_time
                oldest_model_name = f"{model['provider']} {model['display_name']}"
                oldest_date = model["release_date"]
                
    avg_context = total_context // len(free_models_temp) if free_models_temp else 0
    longest_provider = max(prov_counts, key=prov_counts.get) if prov_counts else "N/A"
    
    stats_obj = {
        "providers_count": len(prov_counts),
        "models_count": len(free_models_temp),
        "average_context_length": avg_context,
        "largest_context_window": longest_context,
        "longest_provider": longest_provider,
        "latest_release": f"{newest_model_name} ({newest_date})" if newest_model_name else "N/A",
        "oldest_release": f"{oldest_model_name} ({oldest_date})" if oldest_model_name else "N/A"
    }
    
    # 1. Save versioned envelope
    envelope = {
        "schema_version": 1,
        "generated_at": datetime.now().isoformat(),
        "provider": "OpenRouter",
        "api_retrieved_at": api_retrieved_at,
        "hydra_synced_at": datetime.now().isoformat(),
        "statistics": stats_obj,
        "models": free_models_temp
    }
    
    try:
        with open(models_path, "w", encoding="utf-8") as f:
            json.dump(envelope, f, indent=2)
    except Exception as e:
        print(f"Error saving registry: {e}")
        sys.exit(1)
        
    # 2. Save raw API response
    raw_path = os.path.join(REGISTRY_DIR, "openrouter_models_raw.json")
    try:
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump(raw_response, f, indent=2)
    except Exception as e:
        print(f"Error saving raw response: {e}")
        sys.exit(1)
        
    # 3. Save grouped registry
    grouped = {}
    for model in free_models_temp:
        prov = model["provider"]
        if prov not in grouped:
            grouped[prov] = []
        grouped[prov].append(model)
        
    grouped_path = os.path.join(REGISTRY_DIR, "free_models_grouped.json")
    try:
        with open(grouped_path, "w", encoding="utf-8") as f:
            json.dump(grouped, f, indent=2)
    except Exception as e:
        print(f"Error saving grouped registry: {e}")
        sys.exit(1)
        
    # 4. Export CSV version
    csv_path = os.path.join(REGISTRY_DIR, "free_models.csv")
    try:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "hydra_id", "provider", "display_name", "model_id", 
                "context_length", "input_cost", "output_cost", "release_date"
            ])
            for model in free_models_temp:
                writer.writerow([
                    model["hydra_id"], model["provider"], model["display_name"], 
                    model["model_id"], model["context_length"], model["input_cost"], 
                    model["output_cost"], model["release_date"]
                ])
    except Exception as e:
        print(f"Error exporting CSV: {e}")
        sys.exit(1)
        
    # 5. Save history snapshots
    date_str = datetime.now().strftime("%Y-%m-%d")
    history_path = os.path.join(REGISTRY_DIR, "history", f"{date_str}.json")
    try:
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump(envelope, f, indent=2)
    except Exception as e:
        print(f"Error saving historical snapshot: {e}")
        sys.exit(1)
        
    # 6. Save metadata
    metadata_path = os.path.join(REGISTRY_DIR, "inventory_metadata.json")
    metadata = {
        "provider": "OpenRouter",
        "last_sync": datetime.now().isoformat(),
        "total_models": total_discovered,
        "free_models": len(free_models_temp),
        "version": 1
    }
    try:
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)
    except Exception as e:
        print(f"Error saving metadata: {e}")
        sys.exit(1)
        
    # 7. Generate Diff Report
    added = []
    removed = []
    updated = []
    
    old_dict = {m["model_id"]: m for m in old_models}
    new_dict = {m["model_id"]: m for m in free_models_temp}
    
    for model_id, model in new_dict.items():
        if model_id not in old_dict:
            added.append(model)
            
    for model_id, model in old_dict.items():
        if model_id not in new_dict:
            removed.append(model)
            
    for model_id, new_model in new_dict.items():
        if model_id in old_dict:
            old_model = old_dict[model_id]
            changes = []
            if new_model.get("context_length") != old_model.get("context_length"):
                changes.append(f"Context Length: {format_context(old_model.get('context_length'))} -> {format_context(new_model.get('context_length'))}")
            if new_model.get("input_cost") != old_model.get("input_cost") or new_model.get("output_cost") != old_model.get("output_cost"):
                changes.append(f"Pricing: {old_model.get('input_cost')}/{old_model.get('output_cost')} -> {new_model.get('input_cost')}/{new_model.get('output_cost')}")
            if changes:
                updated.append((new_model, changes))
                
    old_prov_counts = {}
    for m in old_models:
        prov = m.get("provider", "Unknown")
        old_prov_counts[prov] = old_prov_counts.get(prov, 0) + 1
        
    provider_diffs = []
    all_providers = set(old_prov_counts.keys()) | set(prov_counts.keys())
    for prov in sorted(all_providers):
        o_cnt = old_prov_counts.get(prov, 0)
        n_cnt = prov_counts.get(prov, 0)
        if o_cnt != n_cnt:
            diff = n_cnt - o_cnt
            diff_str = f"+{diff}" if diff > 0 else f"{diff}"
            provider_diffs.append((prov, o_cnt, n_cnt, diff_str))
            
    diff_report_path = os.path.join("reports", "Diff_Report.md")
    diff_md = f"""# Hydra Registry Diff Report

**Date:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Comparison Context:** Previous Registry vs. Current Sync

## Added Models
"""
    if added:
        for m in added:
            diff_md += f"* **{m['provider']} {m['display_name']}** (`{m['model_id']}`) - Stable ID: `{m['hydra_id']}`\n"
    else:
        diff_md += "*(none)*\n"
        
    diff_md += "\n## Removed Models\n"
    if removed:
        for m in removed:
            diff_md += f"* **{m['provider']} {m['display_name']}** (`{m['model_id']}`)\n"
    else:
        diff_md += "*(none)*\n"
        
    diff_md += "\n## Updated Models\n"
    if updated:
        for m, changes in updated:
            diff_md += f"* **{m['provider']} {m['display_name']}** (`{m['model_id']}`)\n"
            for change in changes:
                diff_md += f"  * {change}\n"
    else:
        diff_md += "*(none)*\n"
        
    diff_md += "\n## Provider Changes Summary\n"
    if provider_diffs:
        diff_md += "| Provider | Previous Count | Current Count | Change |\n| :--- | :--- | :--- | :--- |\n"
        for p, prev, curr, diff in provider_diffs:
            diff_md += f"| {p} | {prev} | {curr} | {diff} |\n"
    else:
        diff_md += "*(no changes in provider model counts)*\n"
        
    diff_md += "\n---\n*Report generated automatically by Hydra Inventory Synchronizer.*\n"
    try:
        with open(diff_report_path, "w", encoding="utf-8") as f:
            f.write(diff_md)
    except Exception as e:
        print(f"Error saving diff report markdown: {e}")
        
    # 8. Generate Inventory Report
    report_path = os.path.join("reports", "Inventory_Report.md")
    report_md = f"""# Hydra Inventory Report

**Date:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Total Models Discovered:** {total_discovered}
**Free Models Identified:** {len(free_models_temp)}

---

## Providers Summary

| Provider | Free Models |
| :--- | :--- |
"""
    for prov in sorted(prov_counts.keys()):
        report_md += f"| {prov} | {prov_counts[prov]} |\n"
        
    report_md += f"""
---

## Context Statistics

* **Average Context Length:** {avg_context:,} tokens
* **Largest Context Window:** {longest_context:,} tokens ({longest_model_name})

---

## Model Releases

* **Newest Model:** {newest_model_name} ({newest_date})
* **Oldest Model:** {oldest_model_name} ({oldest_date})

---

## Detailed Model Directory

| Hydra ID | Provider | Display Name | Model ID | Context Length | Release Date |
| :--- | :--- | :--- | :--- | :--- | :--- |
"""
    for model in free_models_temp:
        report_md += f"| `{model['hydra_id']}` | {model['provider']} | {model['display_name']} | `{model['model_id']}` | {model['context_length']:,} | {model['release_date']} |\n"
        
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_md)
    except Exception as e:
        print(f"Error saving report markdown: {e}")
        
    print("Registry updated successfully.\n")
    print("Saved:")
    print("registry/free_models.json")
    print("registry/free_models.csv")
    print("registry/free_models_grouped.json")
    print("registry/openrouter_models_raw.json")
    print(f"registry/history/{date_str}.json")
    print("reports/Inventory_Report.md")
    print("reports/Diff_Report.md\n")
    
    # Print statistics
    print("Inventory Summary")
    print("-------------------------")
    print("Providers:")
    for prov in sorted(prov_counts.keys()):
        padding = 18 - len(prov)
        dots = "." * max(1, padding)
        print(f"{prov} {dots} {prov_counts[prov]}")
    print("")
    print(f"Average Context: {avg_context:,} tokens")
    print(f"Longest Context: {longest_context:,} tokens ({longest_model_name})")
    print(f"Newest Model: {newest_model_name} ({newest_date})")
    print(f"Oldest Model: {oldest_model_name} ({oldest_date})")
    print("")
    print("Sync Complete.")

if __name__ == "__main__":
    run_sync()
