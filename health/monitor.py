import os
import sys
import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from typing import List, Dict, Any

# Ensure workspace root is in sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import registry.model_registry as model_reg

# Ensure stdout uses UTF-8 to prevent encoding crashes on Windows console hosts
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

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

def ping_live_model(model_id: str, api_key: str) -> Dict[str, Any]:
    """Pings a live OpenRouter model using a lightweight chat completion request."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    body = {
        "model": model_id,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST"
    )
    
    start_time = time.time()
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            latency = int((time.time() - start_time) * 1000)
            res_body = json.loads(response.read().decode("utf-8"))
            
            # Verify if OpenRouter returned error payload inside 200 OK
            if "error" in res_body:
                err_data = res_body["error"]
                message = err_data.get("message", "Unknown OpenRouter error")
                code = err_data.get("code")
                status = "degraded"
                if code == 429 or "rate" in message.lower():
                    status = "rate_limited"
                return {
                    "status": status,
                    "latency_ms": latency,
                    "http_status": 200,
                    "average_tokens_per_second": None,
                    "last_error": f"OpenRouter API Error (Code: {code}): {message}"
                }
                
            return {
                "status": "healthy",
                "latency_ms": latency,
                "http_status": 200,
                "average_tokens_per_second": 90,
                "last_error": None
            }
    except urllib.error.HTTPError as err:
        latency = int((time.time() - start_time) * 1000)
        try:
            err_body = json.loads(err.read().decode("utf-8"))
            message = err_body.get("error", {}).get("message", err.reason)
            code = err_body.get("error", {}).get("code", err.code)
        except Exception:
            message = err.reason
            code = err.code
            
        status = "degraded"
        if code == 429:
            status = "rate_limited"
        elif code == 401:
            status = "unavailable"
            
        return {
            "status": status,
            "latency_ms": latency,
            "http_status": err.code,
            "average_tokens_per_second": None,
            "last_error": f"HTTP {err.code}: {message}"
        }
    except urllib.error.URLError as err:
        latency = int((time.time() - start_time) * 1000)
        return {
            "status": "unavailable",
            "latency_ms": latency,
            "http_status": None,
            "average_tokens_per_second": None,
            "last_error": f"Connection Error: {err.reason}"
        }
    except Exception as e:
        latency = int((time.time() - start_time) * 1000)
        return {
            "status": "unavailable",
            "latency_ms": latency,
            "http_status": None,
            "average_tokens_per_second": None,
            "last_error": f"Unexpected Error: {str(e)}"
        }

def run_health_checks() -> None:
    print("========================================")
    print("Hydra Health Monitor v1.0")
    print("========================================\n")
    
    load_dotenv()
    
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    mock_mode = os.getenv("HYDRA_MOCK", "").lower() == "true" or not api_key or api_key.startswith("mock")
    
    models = model_reg.get_all()
    if not models:
        print("No models found in registry to check.")
        return
        
    print(f"Loaded {len(models)} models from registry.")
    if mock_mode:
        print("Running in MOCK mode (simulated pings).\n")
    else:
        print("Running in LIVE mode (real HTTP endpoint checks).\n")
        
    print("Starting evaluation pings...\n")
    
    updated_models = []
    for model in models:
        model_id = model["model_id"]
        hydra_id = model["hydra_id"]
        provider = model["provider"]
        display_name = model["display_name"]
        
        # Load previous health metrics for history accumulation
        old_health = model.get("health", {})
        if not isinstance(old_health, dict):
            old_health = {}
        old_successes = old_health.get("consecutive_successes", 0)
        old_failures = old_health.get("consecutive_failures", 0)
        old_history = old_health.get("history", [])
        if not isinstance(old_history, list):
            old_history = []
        old_history = [e for e in old_history if isinstance(e, dict)]
            
        circuit = old_health.get("circuit", "closed")
        opened_at = old_health.get("opened_at")
        retry_after = old_health.get("retry_after")
        
        # Circuit Breaker Checks
        if circuit == "open" and retry_after:
            try:
                retry_time = datetime.fromisoformat(retry_after)
                if datetime.now() < retry_time:
                    print(f"⚡ Circuit OPEN | Skipped ping for {provider} {display_name} ({hydra_id}) | Resets at: {retry_after}\n")
                    # Preserve existing metrics
                    updated_models.append(model)
                    continue
                else:
                    circuit = "half-open"
                    print(f"⚡ Circuit HALF-OPEN | Probing {provider} {display_name} ({hydra_id})...")
            except Exception:
                circuit = "half-open"
                
        if mock_mode:
            # Simulated check
            status = "healthy"
            # Simulate a failure case for Qwen to demonstrate circuit breaker
            if "qwen" in model_id.lower() and old_failures < 3:
                status = "degraded"
                latency = 2000
                last_error = "Simulated test error"
                http_status = 500
            else:
                latency = int(hash(model_id) % 150 + 100)
                last_error = None
                http_status = 200
                
            tokens_per_sec = int(hash(model_id) % 40 + 60)
            time.sleep(0.01)
            
            check_result = {
                "status": status,
                "latency_ms": latency,
                "http_status": http_status,
                "average_tokens_per_second": tokens_per_sec,
                "last_error": last_error
            }
        else:
            # Live HTTP API check
            check_result = ping_live_model(model_id, api_key)
            
        status = check_result["status"]
        latency = check_result["latency_ms"]
        http_status = check_result["http_status"]
        last_error = check_result["last_error"]
        
        # Accumulate metrics & Circuit Breaker Logic
        is_success = (status == "healthy")
        if is_success:
            if circuit == "half-open":
                print(f"⚡ Circuit CLOSED | Probe succeeded for {provider} {display_name} ({hydra_id})!")
            circuit = "closed"
            opened_at = None
            retry_after = None
            new_successes = old_successes + 1
            new_failures = 0
        else:
            new_successes = 0
            new_failures = old_failures + 1
            if new_failures >= 3:
                if circuit != "open":
                    print(f"⚡ Circuit TRIPPED (OPEN) | 3+ failures for {provider} {display_name} ({hydra_id})!")
                circuit = "open"
                status = "unavailable" # force status
                opened_at = datetime.now().isoformat()
                retry_after = (datetime.now() + timedelta(minutes=10)).isoformat()
            else:
                circuit = "closed"
                opened_at = None
                retry_after = None
                
        # Structured Event Log
        event = {
            "timestamp": datetime.now().isoformat(),
            "status": status,
            "latency_ms": latency,
            "http_status": http_status,
            "error": last_error
        }
        old_history.append(event)
        
        if len(old_history) > 10:
            old_history.pop(0)
            
        # Calculate moving success average
        success_count = sum(1 for e in old_history if e.get("status") == "healthy")
        success_rate = round(success_count / len(old_history), 2) if old_history else 0.0
        
        health_metrics = {
            "status": status,
            "latency_ms": latency,
            "last_checked": datetime.now().isoformat(),
            "average_tokens_per_second": check_result.get("average_tokens_per_second"),
            "last_error": last_error,
            "consecutive_successes": new_successes,
            "consecutive_failures": new_failures,
            "history": old_history,
            "success_rate": success_rate,
            "circuit": circuit,
            "opened_at": opened_at,
            "retry_after": retry_after
        }
        
        if status == "healthy":
            print(f"✓ Active | Latency: {latency}ms | Status: {status} | Success Rate: {success_rate} | Circuit: {circuit}\n")
        else:
            print(f"❌ Failed | Latency: {latency}ms | Status: {status} | Success Rate: {success_rate} | Circuit: {circuit} | Error: {last_error}\n")
            
        model["health"] = health_metrics
        updated_models.append(model)
        
    print("Saving updated health metrics back to registry...\n")
    model_reg.save_registry(updated_models)
    print("Health Monitor execution complete. Registry updated.")

if __name__ == "__main__":
    run_health_checks()
