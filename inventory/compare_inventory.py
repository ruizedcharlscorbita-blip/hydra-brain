import os
import sys
import json
import urllib.request
from datetime import datetime
from typing import List, Dict, Any

# Ensure stdout uses UTF-8 to prevent encoding crashes on Windows console hosts
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

REGISTRY_PATH = os.path.join("registry", "free_models.json")

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

def get_mock_models(version: str) -> List[Dict[str, Any]]:
    """Returns mock models list matching OpenRouter API structure for testing."""
    if version == "2":
        return [
            {
                "id": "cohere/north-mini-code:free",
                "name": "Cohere: North Mini Code (free)",
                "context_length": 256000,
                "pricing": {"prompt": "0", "completion": "0"},
                "created": 1735689600
            },
            {
                "id": "google/gemini-flash:free",
                "name": "Google: Gemini Flash (free)",
                "context_length": 256000,  # Context updated: 128K -> 256K
                "pricing": {"prompt": "0", "completion": "0"},
                "created": 1735689600
            },
            {
                "id": "qwen/3:free",
                "name": "Qwen: Qwen 3 (free)",
                "context_length": 32000,
                "pricing": {"prompt": "0", "completion": "0"},
                "created": 1735689600
            },
            {
                "id": "tencent/hy3:free",
                "name": "Tencent: Hy3 (free)",  # Added model
                "context_length": 262144,
                "pricing": {"prompt": "0", "completion": "0"},
                "created": 1735689600
            },
            {
                "id": "poolside/laguna-xs:free",
                "name": "Poolside: Laguna XS (free)",  # Added model
                "context_length": 262144,
                "pricing": {"prompt": "0", "completion": "0"},
                "created": 1735689600
            }
        ]
    else:
        return [
            {
                "id": "cohere/north-mini-code:free",
                "name": "Cohere: North Mini Code (free)",
                "context_length": 256000,
                "pricing": {"prompt": "0", "completion": "0"},
                "created": 1735689600
            },
            {
                "id": "google/gemini-flash:free",
                "name": "Google: Gemini Flash (free)",
                "context_length": 128000,
                "pricing": {"prompt": "0", "completion": "0"},
                "created": 1735689600
            },
            {
                "id": "deepseek/lite:free",
                "name": "Deepseek: DeepSeek Lite (free)",  # Will be removed in v2
                "context_length": 64000,
                "pricing": {"prompt": "0", "completion": "0"},
                "created": 1735689600
            },
            {
                "id": "qwen/3:free",
                "name": "Qwen: Qwen 3 (free)",
                "context_length": 32000,
                "pricing": {"prompt": "0", "completion": "0"},
                "created": 1735689600
            }
        ]

def fetch_latest_free_models(mock_mode: bool) -> List[Dict[str, Any]]:
    """Discovers current free models from OpenRouter endpoint (or mock logic)."""
    raw_models = []
    if mock_mode:
        mock_version = os.getenv("MOCK_INVENTORY_VERSION", "1")
        raw_models = get_mock_models(mock_version)
    else:
        url = "https://openrouter.ai/api/v1/models"
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                res_body = json.loads(response.read().decode("utf-8"))
                raw_models = res_body.get("data", [])
        except Exception as e:
            print(f"Error fetching latest models from OpenRouter: {e}")
            sys.exit(1)
            
    free_models = []
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
            
        is_free = False
        if prompt_cost == 0.0 and output_cost == 0.0:
            is_free = True
        elif "(free)" in name.lower() or model_id.endswith(":free"):
            is_free = True
            
        if is_free:
            provider = ""
            if "/" in model_id:
                provider = model_id.split("/")[0].title()
            elif ":" in name:
                provider = name.split(":")[0].strip()
            else:
                provider = "OpenRouter"
                
            display_name = name
            if ":" in name:
                display_name = name.split(":", 1)[1].strip()
            display_name = display_name.replace("(free)", "").replace("(Free)", "").strip()
            
            created_timestamp = item.get("created")
            release_date = "N/A"
            if created_timestamp:
                try:
                    release_date = datetime.fromtimestamp(created_timestamp).strftime("%Y-%m-%d")
                except Exception:
                    pass
                    
            free_models.append({
                "provider": provider,
                "display_name": display_name,
                "model_id": model_id,
                "context_length": item.get("context_length", 0),
                "input_cost": prompt_cost,
                "output_cost": output_cost,
                "release_date": release_date,
                "updated_at": datetime.now().isoformat(),
                "source": "openrouter"
            })
    return free_models

def format_context(length: int) -> str:
    """Formats context length into K (thousands) or M (millions) display string."""
    if length is None:
        return "N/A"
    if length >= 1000000:
        if length % 1048576 == 0:
            return f"{length // 1048576}M"
        return f"{length // 1000}K"
    return f"{length // 1000}K"

def load_models_from_file(file_path: str) -> List[Dict[str, Any]]:
    """Loads models list supporting list or envelope structures."""
    if not os.path.exists(file_path):
        print(f"Error: Snapshot file not found: {file_path}")
        sys.exit(1)
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict) and "models" in data:
                return data["models"]
            elif isinstance(data, list):
                return data
            else:
                print(f"Error: Invalid registry structure in {file_path}")
                sys.exit(1)
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
        sys.exit(1)

def compare_inventories() -> None:
    print("Inventory Comparison\n")
    
    registry_models = []
    latest_models = []
    
    # Check if snapshot files are provided as arguments
    if len(sys.argv) == 3:
        file1 = sys.argv[1]
        file2 = sys.argv[2]
        print(f"Comparing snapshot: {file1}")
        print(f"With snapshot:      {file2}\n")
        registry_models = load_models_from_file(file1)
        latest_models = load_models_from_file(file2)
    elif len(sys.argv) > 1:
        print("Usage: python inventory/compare_inventory.py [<snapshot_1.json> <snapshot_2.json>]")
        sys.exit(1)
    else:
        # Standard flow: Load local registry and fetch live OpenRouter
        registry_models = []
        if os.path.exists(REGISTRY_PATH):
            registry_models = load_models_from_file(REGISTRY_PATH)
            
        load_dotenv()
        api_key = os.getenv("OPENROUTER_API_KEY", "")
        mock_mode = os.getenv("HYDRA_MOCK", "").lower() == "true" or not api_key or api_key.startswith("mock")
        
        latest_models = fetch_latest_free_models(mock_mode)
        
    # Process differences
    registry_dict = {m["model_id"]: m for m in registry_models}
    latest_dict = {m["model_id"]: m for m in latest_models}
    
    added = []
    removed = []
    updated = []
    
    # Additions
    for model_id, model in latest_dict.items():
        if model_id not in registry_dict:
            added.append(model)
            
    # Removals
    for model_id, model in registry_dict.items():
        if model_id not in latest_dict:
            removed.append(model)
            
    # Updates
    for model_id, latest_model in latest_dict.items():
        if model_id in registry_dict:
            reg_model = registry_dict[model_id]
            changes = []
            
            # Check context length
            if latest_model.get("context_length") != reg_model.get("context_length"):
                changes.append({
                    "field": "Context",
                    "old": format_context(reg_model.get("context_length")),
                    "new": format_context(latest_model.get("context_length"))
                })
                
            # Check pricing
            if (latest_model.get("input_cost") != reg_model.get("input_cost") or 
                latest_model.get("output_cost") != reg_model.get("output_cost")):
                changes.append({
                    "field": "Pricing",
                    "old": f"{reg_model.get('input_cost')}/{reg_model.get('output_cost')}",
                    "new": f"{latest_model.get('input_cost')}/{latest_model.get('output_cost')}"
                })
                
            if changes:
                updated.append((latest_model, changes))
                
    # Format Output
    print("Added")
    print("-------------------------")
    if added:
        for model in added:
            print(f"{model['provider']} {model['display_name']}")
    else:
        print("(none)")
    print("")
    
    print("Removed")
    print("-------------------------")
    if removed:
        for model in removed:
            print(f"{model['provider']} {model['display_name']}")
    else:
        print("(none)")
    print("")
    
    print("Updated")
    print("-------------------------")
    if updated:
        for model, changes in updated:
            print(f"{model['provider']} {model['display_name']}")
            print("")
            for change in changes:
                print(f"{change['field']}:")
                print(f"{change['old']} → {change['new']}")
            print("")
    else:
        print("(none)")
    print("")
    
    print("Comparison Complete.")

if __name__ == "__main__":
    compare_inventories()
