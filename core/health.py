import logging
from typing import Dict, Any
from providers.openrouter import OpenRouterProvider

logger = logging.getLogger("hydra")

class HealthChecker:
    def check_head(self, head: Dict[str, Any]) -> str:
        """Checks and returns the health status of a registered head.
        
        Args:
            head: A dictionary representing the head's configuration details.
            
        Returns:
            One of: 'AVAILABLE', 'UNAVAILABLE', 'RATE_LIMITED', 'FAILED'.
        """
        head_id = head.get("id")
        provider_name = head.get("provider")
        model_name = head.get("model")
        
        logger.debug(f"Initiating health check for head '{head_id}' via '{provider_name}'")
        
        if provider_name == "openrouter":
            try:
                provider = OpenRouterProvider(model_name, head_id)
                status = provider.health_check()
                logger.info(f"Health check result for head '{head_id}': {status}")
                return status
            except Exception as e:
                logger.error(f"Exception during health check for head '{head_id}': {e}")
                return "FAILED"
        else:
            logger.warning(f"Unsupported provider '{provider_name}' for head '{head_id}'")
            return "UNAVAILABLE"
