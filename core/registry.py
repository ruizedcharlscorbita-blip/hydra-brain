import json
import os
from typing import List, Dict, Any

class HeadRegistry:
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.heads: List[Dict[str, Any]] = []
        self.load_heads()

    def load_heads(self) -> None:
        """Loads and parses the heads from the JSON config file."""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Configuration file not found at: {self.config_path}")
        
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.heads = data.get("heads", [])
        except json.JSONDecodeError as e:
            raise ValueError(f"Configuration file at {self.config_path} contains invalid JSON: {e}")
        except Exception as e:
            raise RuntimeError(f"Failed to read configuration file: {e}")
        
        self.validate_heads()

    def validate_heads(self) -> None:
        """Validates that the loaded heads match the required schema."""
        if not isinstance(self.heads, list):
            raise ValueError("Configuration root must contain a 'heads' list.")
            
        seen_ids = set()
        for idx, head in enumerate(self.heads):
            if not isinstance(head, dict):
                raise ValueError(f"Head at index {idx} must be a JSON object.")
                
            head_id = head.get("id")
            if not head_id or not isinstance(head_id, str):
                raise ValueError(f"Head at index {idx} must have a non-empty string 'id'.")
                
            if head_id in seen_ids:
                raise ValueError(f"Duplicate head ID found in config: '{head_id}'.")
            seen_ids.add(head_id)
            
            provider = head.get("provider")
            if provider not in ("openrouter",):
                raise ValueError(f"Head '{head_id}' has unsupported provider '{provider}'.")
                
            model = head.get("model")
            if not model or not isinstance(model, str):
                raise ValueError(f"Head '{head_id}' must have a non-empty string 'model'.")
                
            priority = head.get("priority")
            if priority is None or not isinstance(priority, int) or priority < 1:
                raise ValueError(f"Head '{head_id}' must have an integer 'priority' >= 1.")
                
            cooldown = head.get("cooldown_seconds")
            if cooldown is not None:
                if not isinstance(cooldown, int) or cooldown < 0:
                    raise ValueError(f"Head '{head_id}' 'cooldown_seconds' must be a non-negative integer.")

    def get_all_heads(self) -> List[Dict[str, Any]]:
        """Returns all loaded heads."""
        return self.heads

    def get_head_by_id(self, head_id: str) -> Dict[str, Any]:
        """Finds and returns a head by its ID, raising ValueError if not found."""
        for head in self.heads:
            if head.get("id") == head_id:
                return head
        raise ValueError(f"Head '{head_id}' not found in registry.")
