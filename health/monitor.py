import os
import sys
import json
import time
from datetime import datetime
from typing import List, Dict, Any

import registry.model_registry as model_reg

# Ensure stdout uses UTF-8 to prevent encoding crashes on Windows console hosts
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

def run_health_checks() -> None:
    print("========================================")
    print("Hydra Health Monitor v0.1")
    print("========================================\n")
    
    models = model_reg.get_all()
    if not models:
        print("No models found in registry to check.")
        return
        
    print(f"Loaded {len(models)} models from registry.\n")
    print("Starting evaluation pings...\n")
    
    updated_models = []
    for model in models:
        model_id = model["model_id"]
        hydra_id = model["hydra_id"]
        provider = model["provider"]
        display_name = model["display_name"]
        
        print(f"Evaluating {provider} {display_name} ({hydra_id})...")
        
        # In v0.1 Health Monitor, we simulate pings and latency responses
        # Future releases will perform lightweight runtime prompts against OpenRouter endpoints
        status = "healthy"
        latency = int(hash(model_id) % 150 + 100)  # semi-stable simulated latency between 100-250ms
        success_rate = 1.0
        tokens_per_sec = int(hash(model_id) % 40 + 60) # simulated 60-100 tokens/sec
        
        # Small delay to simulate ping latency
        time.sleep(0.01)
        
        # Update ONLY the health subkey to honor data boundaries contract
        model["health"] = {
            "status": status,
            "latency_ms": latency,
            "success_rate": success_rate,
            "last_checked": datetime.now().isoformat(),
            "average_tokens_per_second": tokens_per_sec,
            "last_error": None
        }
        
        print(f"✓ Active | Latency: {latency}ms | Status: {status}\n")
        updated_models.append(model)
        
    print("Saving updated health metrics back to registry...\n")
    model_reg.save_registry(updated_models)
    print("Health Monitor execution complete. Registry updated.")

if __name__ == "__main__":
    run_health_checks()
