"""
router.py — Hydra Brain legacy failover router
===============================================

Legacy failover router for head configuration selection (v0.2.0 compatibility).
"""

import logging
from typing import Dict, List, Any, Optional

from core.state import StateManager

logger = logging.getLogger("hydra")


class Router:
    """
    Selects the best available head config based on priority and cooldown status.
    Used for static failover routing.
    """

    def select_head(
        self,
        heads: List[Dict[str, Any]],
        health_status: Dict[str, Any],
        state_manager: StateManager,
    ) -> Dict[str, Any]:
        sorted_heads = sorted(heads, key=lambda h: h.get("priority", 999))
        
        for head in sorted_heads:
            head_id = head.get("id")
            
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
