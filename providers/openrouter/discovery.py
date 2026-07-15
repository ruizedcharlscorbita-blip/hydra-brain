import os
import json
import urllib.request
from datetime import datetime
from typing import List, Dict, Any

class OpenRouterDiscovery:
    def __init__(self):
        self.api_key = os.getenv("OPENROUTER_API_KEY", "")

    def _is_mock_enabled(self) -> bool:
        mock_env = os.getenv("HYDRA_MOCK", "").lower() == "true"
        mock_key = not self.api_key or self.api_key.startswith("mock")
        return mock_env or mock_key

    def discover_models(self) -> List[Dict[str, Any]]:
        """Fetches available models from OpenRouter and normalizes free models."""
        if self._is_mock_enabled():
            # Return mock models for testing and development
            return [
                {
                    "provider": "Tencent",
                    "display_name": "Hy3",
                    "model_id": "tencent/hy3:free",
                    "free": True,
                    "context": 262144,
                    "input_cost": 0.0,
                    "output_cost": 0.0,
                    "release_date": "2024-12-30",
                    "discovery_timestamp": datetime.now().isoformat()
                },
                {
                    "provider": "Cohere",
                    "display_name": "North Mini Code",
                    "model_id": "cohere/north-mini-code:free",
                    "free": True,
                    "context": 128000,
                    "input_cost": 0.0,
                    "output_cost": 0.0,
                    "release_date": "2025-01-15",
                    "discovery_timestamp": datetime.now().isoformat()
                },
                {
                    "provider": "Deepseek",
                    "display_name": "DeepSeek V3",
                    "model_id": "deepseek/v3:free",
                    "free": True,
                    "context": 64000,
                    "input_cost": 0.0,
                    "output_cost": 0.0,
                    "release_date": "2024-12-25",
                    "discovery_timestamp": datetime.now().isoformat()
                },
                {
                    "provider": "Qwen",
                    "display_name": "Qwen 3",
                    "model_id": "qwen/3:free",
                    "free": True,
                    "context": 32000,
                    "input_cost": 0.0,
                    "output_cost": 0.0,
                    "release_date": "2025-02-10",
                    "discovery_timestamp": datetime.now().isoformat()
                },
                {
                    "provider": "Google",
                    "display_name": "Gemini Flash",
                    "model_id": "google/gemini-flash:free",
                    "free": True,
                    "context": 1048576,
                    "input_cost": 0.0,
                    "output_cost": 0.0,
                    "release_date": "2024-05-14",
                    "discovery_timestamp": datetime.now().isoformat()
                }
            ]

        url = "https://openrouter.ai/api/v1/models"
        req = urllib.request.Request(url, method="GET")
        
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                res_body = json.loads(response.read().decode("utf-8"))
                models_data = res_body.get("data", [])
                
                free_models = []
                for item in models_data:
                    model_id = item.get("id", "")
                    name = item.get("name", "")
                    pricing = item.get("pricing", {})
                    
                    # Parse input/output pricing costs
                    prompt_price = 0.0
                    comp_price = 0.0
                    try:
                        prompt_price = float(pricing.get("prompt", 0.0))
                        comp_price = float(pricing.get("completion", 0.0))
                    except (ValueError, TypeError):
                        pass
                        
                    # Filter free models based on name/id or pricing structure
                    is_free = (
                        model_id.endswith(":free") or 
                        "(free)" in name.lower() or 
                        (prompt_price == 0.0 and comp_price == 0.0)
                    )
                    
                    if is_free:
                        # Extract provider name
                        provider = ""
                        if "/" in model_id:
                            provider = model_id.split("/")[0].title()
                        elif ":" in name:
                            provider = name.split(":")[0].strip()
                        else:
                            provider = "OpenRouter"
                            
                        # Extract clean display name (stripping provider prefix & free suffix)
                        display_name = name
                        if ":" in name:
                            display_name = name.split(":", 1)[1].strip()
                        display_name = display_name.replace("(free)", "").replace("(Free)", "").strip()
                        
                        # Handle release date
                        created_timestamp = item.get("created")
                        release_date = None
                        if created_timestamp:
                            try:
                                release_date = datetime.fromtimestamp(created_timestamp).strftime("%Y-%m-%d")
                            except Exception:
                                pass
                                
                        free_models.append({
                            "provider": provider,
                            "display_name": display_name,
                            "model_id": model_id,
                            "free": True,
                            "context": item.get("context_length", 0),
                            "input_cost": prompt_price,
                            "output_cost": comp_price,
                            "release_date": release_date,
                            "discovery_timestamp": datetime.now().isoformat()
                        })
                        
                return free_models
        except Exception as e:
            raise RuntimeError(f"OpenRouter Discovery Error: {e}")
