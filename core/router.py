import logging
from typing import List, Dict, Any

from core.state import StateManager

logger = logging.getLogger("hydra")

class Router:
    def select_head(self, heads: List[Dict[str, Any]], health_status: Dict[str, str], state_manager: StateManager) -> Dict[str, Any]:
        """Selects the best available head based on priority and cooldown status.
        
        Priority is sorted ascending (lower priority value means higher precedence, e.g. 1 is tried before 2).
        Only heads with status 'AVAILABLE' that are not in cooldown are considered.
        
        Args:
            heads: List of heads from registry.
            health_status: Map from head ID to its health status string.
            state_manager: The active StateManager instance.
            
        Returns:
            The selected head configuration dictionary.
            
        Raises:
            RuntimeError: If no available heads are found.
        """
        # Sort heads by priority. Defaults to a high number if priority is missing.
        sorted_heads = sorted(heads, key=lambda h: h.get("priority", 999))
        
        for head in sorted_heads:
            head_id = head.get("id")
            
            # Skip heads currently in cooldown
            if state_manager.is_in_cooldown(head_id):
                cooldown_remaining = state_manager.get_cooldown_remaining(head_id)
                logger.debug(f"Router skipped head '{head_id}' because it is in cooldown ({cooldown_remaining:.1f}s remaining)")
                continue
                
            status_entry = health_status.get(head_id, "FAILED")
            status = status_entry.get("status", "FAILED") if isinstance(status_entry, dict) else status_entry
            
            if status == "AVAILABLE":
                logger.info(f"Router selected head '{head_id}' with priority {head.get('priority')}")
                return head
            else:
                logger.debug(f"Router skipped head '{head_id}' (status: {status})")
                
        raise RuntimeError("No available heads found.")
