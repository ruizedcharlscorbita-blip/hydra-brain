import os
import sys
import json
import re

# Ensure stdout uses UTF-8 to prevent encoding crashes on Windows console hosts
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

REGISTRY_PATH = os.path.join("registry", "free_models.json")

def run_validation() -> None:
    print("Inventory Validation\n")
    
    registry_path = REGISTRY_PATH
    
    # 1. Verify JSON file exists
    if not os.path.exists(registry_path):
        print(f"Error: Registry file not found at {registry_path}")
        sys.exit(1)
        
    # 2. Verify JSON structure is valid
    try:
        with open(registry_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON structure in registry: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading registry: {e}")
        sys.exit(1)
        
    print("✓ JSON valid\n")
    
    # 3. Verify envelope structure
    if not isinstance(data, dict):
        print("Error: Registry root must be a JSON object (envelope).")
        sys.exit(1)
        
    schema_version = data.get("schema_version")
    if schema_version is None or schema_version != 1:
        print(f"Error: Invalid or missing 'schema_version'. Expected 1, got: {schema_version}")
        sys.exit(1)
        
    if "provider" not in data or data["provider"] != "OpenRouter":
        print(f"Error: Invalid or missing envelope 'provider'. Expected 'OpenRouter', got: {data.get('provider')}")
        sys.exit(1)
        
    if "generated_at" not in data:
        print("Error: Missing envelope 'generated_at' timestamp.")
        sys.exit(1)
        
    models = data.get("models")
    if not isinstance(models, list):
        print("Error: Missing or invalid 'models' list in envelope.")
        sys.exit(1)
        
    seen_model_ids = set()
    seen_hydra_ids = set()
    duplicates_model_id = []
    duplicates_hydra_id = []
    
    hydra_id_pattern = re.compile(r"^hydra-or-[0-9a-f]{8}$")
    
    for idx, model in enumerate(models):
        if not isinstance(model, dict):
            print(f"Error: Model entry at index {idx} is not a JSON object.")
            sys.exit(1)
            
        model_id = model.get("model_id")
        hydra_id = model.get("hydra_id")
        provider = model.get("provider")
        display_name = model.get("display_name")
        context_length = model.get("context_length")
        input_cost = model.get("input_cost")
        output_cost = model.get("output_cost")
        
        # Verify provider and display name present
        if not provider or not isinstance(provider, str):
            print(f"Error: Model entry at index {idx} has missing or invalid 'provider'.")
            sys.exit(1)
            
        if not display_name or not isinstance(display_name, str):
            print(f"Error: Model '{model_id}' (index {idx}) has missing or invalid 'display_name'.")
            sys.exit(1)
            
        # Verify unique model IDs
        if not model_id or not isinstance(model_id, str):
            print(f"Error: Model entry at index {idx} has missing or invalid 'model_id'.")
            sys.exit(1)
            
        if model_id in seen_model_ids:
            duplicates_model_id.append(model_id)
        seen_model_ids.add(model_id)
        
        # Verify unique hydra IDs and format (hydra-or-XXXXX)
        if not hydra_id or not isinstance(hydra_id, str):
            print(f"Error: Model '{model_id}' has missing or invalid 'hydra_id'.")
            sys.exit(1)
            
        if not hydra_id_pattern.match(hydra_id):
            print(f"Error: Model '{model_id}' has invalid 'hydra_id' format. Expected 'hydra-or-XXXXX', got '{hydra_id}'")
            sys.exit(1)
            
        if hydra_id in seen_hydra_ids:
            duplicates_hydra_id.append(hydra_id)
        seen_hydra_ids.add(hydra_id)
        
        # Verify context length
        if context_length is None or not isinstance(context_length, int) or context_length < 0:
            print(f"Error: Model '{model_id}' has invalid 'context_length': {context_length}")
            sys.exit(1)
            
        # Verify pricing costs are present and numeric
        if input_cost is None or not isinstance(input_cost, (int, float)) or input_cost < 0:
            print(f"Error: Model '{model_id}' has invalid 'input_cost': {input_cost}")
            sys.exit(1)
            
        if output_cost is None or not isinstance(output_cost, (int, float)) or output_cost < 0:
            print(f"Error: Model '{model_id}' has invalid 'output_cost': {output_cost}")
            sys.exit(1)
            
        # Validate additional fields
        if "description" not in model or not isinstance(model["description"], str):
            print(f"Error: Model '{model_id}' has missing or invalid 'description'.")
            sys.exit(1)
            
        if "architecture" not in model or not isinstance(model["architecture"], dict):
            print(f"Error: Model '{model_id}' has missing or invalid 'architecture'.")
            sys.exit(1)
            
        if "modalities" not in model or not isinstance(model["modalities"], list):
            print(f"Error: Model '{model_id}' has missing or invalid 'modalities'.")
            sys.exit(1)
            
        if "pricing" not in model or not isinstance(model["pricing"], dict):
            print(f"Error: Model '{model_id}' has missing or invalid 'pricing'.")
            sys.exit(1)
            
        if "free" not in model or model["free"] is not True:
            print(f"Error: Model '{model_id}' has invalid or missing 'free' flag.")
            sys.exit(1)
            
        # Validate capabilities block
        capabilities = model.get("capabilities")
        if not isinstance(capabilities, dict):
            print(f"Error: Model '{model_id}' has missing or invalid 'capabilities' block.")
            sys.exit(1)
            
        required_caps = {
            "coding", "reasoning", "writing", "analysis", "vision", 
            "chat", "tool_calling", "json_output", "streaming"
        }
        for cap_key in required_caps:
            if cap_key not in capabilities:
                print(f"Error: Model '{model_id}' is missing capability: '{cap_key}'")
                sys.exit(1)
            score = capabilities[cap_key]
            if not isinstance(score, int) or not (0 <= score <= 5):
                print(f"Error: Model '{model_id}' has invalid score for capability '{cap_key}': {score}. Expected integer between 0 and 5.")
                sys.exit(1)
            
        # Validate health block
        health = model.get("health")
        if not isinstance(health, dict):
            print(f"Error: Model '{model_id}' has missing or invalid 'health' block.")
            sys.exit(1)
            
        valid_statuses = {"unknown", "healthy", "rate_limited", "degraded", "unavailable"}
        status = health.get("status")
        if status not in valid_statuses:
            print(f"Error: Model '{model_id}' has invalid health status: '{status}'")
            sys.exit(1)
            
        consec_succ = health.get("consecutive_successes")
        if consec_succ is not None and (not isinstance(consec_succ, int) or consec_succ < 0):
            print(f"Error: Model '{model_id}' has invalid 'consecutive_successes': {consec_succ}")
            sys.exit(1)
            
        consec_fail = health.get("consecutive_failures")
        if consec_fail is not None and (not isinstance(consec_fail, int) or consec_fail < 0):
            print(f"Error: Model '{model_id}' has invalid 'consecutive_failures': {consec_fail}")
            sys.exit(1)
            
        circuit = health.get("circuit")
        valid_circuits = {"closed", "open", "half-open"}
        if circuit is not None and circuit not in valid_circuits:
            print(f"Error: Model '{model_id}' has invalid circuit state: '{circuit}'")
            sys.exit(1)
            
        history = health.get("history")
        if history is not None:
            if not isinstance(history, list):
                print(f"Error: Model '{model_id}' has invalid 'history' type. Expected list.")
                sys.exit(1)
            for event_idx, event in enumerate(history):
                if not isinstance(event, dict):
                    print(f"Error: Model '{model_id}' history event at index {event_idx} is not a dictionary.")
                    sys.exit(1)
                if "timestamp" not in event or "status" not in event or "latency_ms" not in event:
                    print(f"Error: Model '{model_id}' history event at index {event_idx} is missing required fields.")
                    sys.exit(1)
                    
        success_rate = health.get("success_rate")
        if success_rate is not None and (not isinstance(success_rate, (int, float)) or not (0.0 <= success_rate <= 1.0)):
            print(f"Error: Model '{model_id}' has invalid 'success_rate': {success_rate}")
            sys.exit(1)
            
    if duplicates_model_id:
        print(f"Error: Duplicate model IDs found: {', '.join(duplicates_model_id)}")
        sys.exit(1)
        
    if duplicates_hydra_id:
        print(f"Error: Duplicate hydra IDs found: {', '.join(duplicates_hydra_id)}")
        sys.exit(1)
        
    print("✓ No duplicate IDs\n")
    print("✓ All providers present\n")
    print("✓ All model IDs unique\n")
    print("✓ Registry integrity verified")
    sys.exit(0)

if __name__ == "__main__":
    run_validation()
