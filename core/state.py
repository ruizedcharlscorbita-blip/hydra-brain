import json
import os
from datetime import datetime, timedelta
from typing import Dict, Any

class StateManager:
    def __init__(self, state_path: str):
        self.state_path = state_path
        self.state: Dict[str, Any] = {"heads": {}}
        self.load_state()

    def load_state(self) -> None:
        """Loads the state dictionary from the JSON state file."""
        if not os.path.exists(self.state_path):
            # Ensure directories are created if dirname is not empty
            dir_name = os.path.dirname(self.state_path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            self.save_state()
            return
        
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                self.state = json.load(f)
                if "heads" not in self.state:
                    self.state["heads"] = {}
        except Exception:
            # Re-initialize on load failure to prevent crashes
            self.state = {"heads": {}}
            self.save_state()

    def save_state(self) -> None:
        """Saves the active state dictionary to the JSON state file."""
        try:
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2)
        except Exception:
            pass

    def get_head_state(self, head_id: str) -> Dict[str, Any]:
        """Gets or initializes the state tracking metadata for a given head ID."""
        if head_id not in self.state["heads"]:
            self.state["heads"][head_id] = {
                "status": "UNKNOWN",
                "failures": 0,
                "successes": 0,
                "last_failure": None,
                "http_status": None,
                "provider_code": None,
                "provider_message": None,
                "latency_ms": None,
                "last_used": None,
                "cooldown_until": None
            }
        return self.state["heads"][head_id]

    def record_success(self, head_id: str, latency_ms: int = None) -> None:
        """Records a successful execution, resetting status to AVAILABLE and clearing cooldowns."""
        hstate = self.get_head_state(head_id)
        hstate["successes"] += 1
        hstate["status"] = "AVAILABLE"
        hstate["cooldown_until"] = None
        hstate["last_used"] = datetime.now().isoformat()
        if latency_ms is not None:
            hstate["latency_ms"] = latency_ms
            hstate["http_status"] = 200
            hstate["provider_code"] = None
            hstate["provider_message"] = None
        self.save_state()

    def record_failure(self, head_id: str, diagnostics: Any, cooldown_seconds: int = 900) -> None:
        """Records a failed execution, incrementing failure counts and setting a cooldown period."""
        hstate = self.get_head_state(head_id)
        hstate["failures"] += 1
        
        if isinstance(diagnostics, dict):
            status = diagnostics.get("status", "FAILED")
            hstate["status"] = status
            hstate["last_failure"] = status
            hstate["http_status"] = diagnostics.get("http_status")
            hstate["provider_code"] = diagnostics.get("provider_code")
            hstate["provider_message"] = diagnostics.get("provider_message")
            hstate["latency_ms"] = diagnostics.get("latency_ms")
        else:
            status = str(diagnostics)
            hstate["status"] = status
            hstate["last_failure"] = status
            hstate["http_status"] = None
            hstate["provider_code"] = None
            hstate["provider_message"] = None
            hstate["latency_ms"] = None
            
        now = datetime.now()
        hstate["last_used"] = now.isoformat()
        
        cooldown_time = now + timedelta(seconds=cooldown_seconds)
        hstate["cooldown_until"] = cooldown_time.isoformat()
        self.save_state()

    def update_diagnostics(self, head_id: str, diagnostics: Dict[str, Any]) -> None:
        """Updates the status and other telemetry fields of the head from health diagnostics."""
        hstate = self.get_head_state(head_id)
        status = diagnostics.get("status", "UNKNOWN")
        hstate["status"] = status
        hstate["http_status"] = diagnostics.get("http_status")
        hstate["provider_code"] = diagnostics.get("provider_code")
        hstate["provider_message"] = diagnostics.get("provider_message")
        hstate["latency_ms"] = diagnostics.get("latency_ms")
        
        if status == "AVAILABLE":
            hstate["cooldown_until"] = None
        self.save_state()

    def update_status(self, head_id: str, status: str) -> None:
        """Updates the status of the head (backward compatibility)."""
        hstate = self.get_head_state(head_id)
        hstate["status"] = status
        if status == "AVAILABLE":
            hstate["cooldown_until"] = None
        self.save_state()

    def is_in_cooldown(self, head_id: str) -> bool:
        """Checks if a head is currently in an active cooldown period."""
        hstate = self.get_head_state(head_id)
        cooldown_until_str = hstate.get("cooldown_until")
        if not cooldown_until_str:
            return False
        
        try:
            cooldown_until = datetime.fromisoformat(cooldown_until_str)
            return datetime.now() < cooldown_until
        except Exception:
            return False

    def get_cooldown_remaining(self, head_id: str) -> float:
        """Returns the remaining cooldown time in seconds, or 0.0 if not in cooldown."""
        hstate = self.get_head_state(head_id)
        cooldown_until_str = hstate.get("cooldown_until")
        if not cooldown_until_str:
            return 0.0
        
        try:
            cooldown_until = datetime.fromisoformat(cooldown_until_str)
            remaining = (cooldown_until - datetime.now()).total_seconds()
            return max(0.0, remaining)
        except Exception:
            return 0.0
