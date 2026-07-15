import logging
import time
from datetime import datetime
from typing import Dict, Any, List, Optional
from core.registry import HeadRegistry
from core.health import HealthChecker
from core.router import Router
from core.state import StateManager
from providers.openrouter import OpenRouterProvider
from providers.base import ProviderError

logger = logging.getLogger("hydra")

def format_time_only(iso_str: str) -> str:
    """Extracts HH:MM format from an ISO string, or returns N/A."""
    if not iso_str:
        return "N/A"
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%H:%M")
    except Exception:
        return iso_str

def format_decision_log(prompt: str, heads: List[Dict[str, Any]], health_status: Dict[str, Dict[str, Any]], selected_head: Optional[Dict[str, Any]], state_manager: StateManager) -> str:
    """Generates a structured HYDRA DECISION trace for the logger."""
    lines = [
        "========== HYDRA DECISION ==========",
        "",
        "Prompt",
        "------------------------------------",
        prompt,
        ""
    ]
    
    for idx, head in enumerate(heads):
        head_id = head["id"]
        readable_name = head_id.replace("-", " ").title()
        diag = health_status[head_id]
        
        lines.append(f"Head: {readable_name}")
        lines.append("")
        lines.append("Status:")
        lines.append(diag.get("status", "UNKNOWN"))
        lines.append("")
        lines.append("HTTP:")
        lines.append(str(diag.get("http_status")) if diag.get("http_status") is not None else "None")
        lines.append("")
        lines.append("Latency:")
        lines.append(f"{diag.get('latency_ms')} ms" if diag.get("latency_ms") is not None else "None ms")
        lines.append("")
        
        if diag.get("status") != "AVAILABLE" and diag.get("provider_message"):
            lines.append("Reason:")
            lines.append(diag.get("provider_message"))
            lines.append("")
            
        lines.append("Action:")
        if selected_head and head_id == selected_head["id"]:
            lines.append("SELECTED")
        elif state_manager.is_in_cooldown(head_id):
            cooldown_remaining = state_manager.get_cooldown_remaining(head_id)
            cooldown_min = int(round(cooldown_remaining / 60.0))
            if cooldown_min == 0 and cooldown_remaining > 0:
                cooldown_min = 1
            if cooldown_min == 0:
                cooldown_min = head.get("cooldown_seconds", 900) // 60
            lines.append(f"Cooldown {cooldown_min} minutes")
        else:
            lines.append("SKIPPED")
            
        if idx < len(heads) - 1:
            lines.append("")
            lines.append("------------------------------------")
            lines.append("")
            
    lines.append("====================================")
    return "\n".join(lines)

def print_cli_dashboard(heads: List[Dict[str, Any]], health_status: Dict[str, Dict[str, Any]], selected_head: Optional[Dict[str, Any]], state_manager: StateManager) -> None:
    """Prints a detailed infrastructure telemetry dashboard to the console."""
    print("=========================================")
    print("HYDRA BRAIN")
    print("=========================================\n")
    
    for idx, head in enumerate(heads):
        head_id = head["id"]
        readable_name = head_id.replace("-", " ").title()
        provider_name = head["provider"].replace("-", " ").title()
        priority = head["priority"]
        
        diag = health_status[head_id]
        hstate = state_manager.get_head_state(head_id)
        
        print(f"Head {idx + 1}")
        print("-----------------------------------------")
        print(f"Name       : {readable_name}")
        print(f"Provider   : {provider_name}")
        print(f"Priority   : {priority}\n")
        
        print("Health")
        print(f"Status     : {diag.get('status')}")
        http_val = diag.get("http_status")
        print(f"HTTP       : {http_val if http_val is not None else 'None'}")
        latency_val = diag.get("latency_ms")
        print(f"Latency    : {f'{latency_val} ms' if latency_val is not None else 'None ms'}\n")
        
        if diag.get("status") != "AVAILABLE" and diag.get("provider_message"):
            print("Reason")
            print(f"{diag.get('provider_message')}\n")
            
        print("Decision")
        if selected_head and head_id == selected_head["id"]:
            print("SELECTED")
        elif state_manager.is_in_cooldown(head_id):
            cooldown_until_str = hstate.get("cooldown_until")
            cooldown_time = format_time_only(cooldown_until_str)
            print(f"Cooldown until {cooldown_time}")
        else:
            print("SKIPPED")
        print("")

class HydraController:
    def __init__(self, config_path: str, state_path: str):
        self.registry = HeadRegistry(config_path)
        self.state_manager = StateManager(state_path)
        self.health_checker = HealthChecker()
        self.router = Router()

    def handle_request(self, prompt: str) -> str:
        """Coordinates head selection and generation with runtime fallback.
        
        Args:
            prompt: The user query string.
            
        Returns:
            The generated response string.
            
        Raises:
            RuntimeError: If all heads fail to generate a response.
        """
        logger.info(f"Received generation request: '{prompt}'")
        
        # 1. Load and validate configuration
        self.registry.load_heads()
        self.registry.validate_heads()
        heads = self.registry.get_all_heads()
        if not heads:
            logger.error("No registered heads found.")
            raise RuntimeError("No heads registered.")

        # 2. Check health of all heads (skipping those in cooldown)
        health_status = {}
        for head in heads:
            head_id = head["id"]
            if self.state_manager.is_in_cooldown(head_id):
                hstate = self.state_manager.get_head_state(head_id)
                health_status[head_id] = {
                    "status": hstate.get("status", "FAILED"),
                    "http_status": hstate.get("http_status"),
                    "latency_ms": hstate.get("latency_ms"),
                    "provider": head["provider"],
                    "model": head["model"],
                    "provider_code": hstate.get("provider_code"),
                    "provider_message": hstate.get("provider_message")
                }
                logger.info(f"Head '{head_id}' is in cooldown. Diagnostic status remains: {health_status[head_id]['status']}")
            else:
                status_diag = self.health_checker.check_head(head)
                health_status[head_id] = status_diag
                status = status_diag.get("status", "FAILED")
                if status in ("RATE_LIMITED", "FAILED"):
                    cooldown_sec = head.get("cooldown_seconds", 900)
                    self.state_manager.record_failure(head_id, status_diag, cooldown_seconds=cooldown_sec)
                else:
                    self.state_manager.update_diagnostics(head_id, status_diag)

        # 3. Dynamic routing and execution with fallback
        tried_heads = set()
        while True:
            remaining_heads = [h for h in heads if h["id"] not in tried_heads]
            
            selected_head = None
            try:
                selected_head = self.router.select_head(remaining_heads, health_status, self.state_manager)
            except RuntimeError:
                # We will log the decision trace and print dashboard before raising error
                pass

            # Log Hydra Decision
            decision_log = format_decision_log(prompt, heads, health_status, selected_head, self.state_manager)
            logger.info(decision_log)

            # Display infrastructure CLI dashboard
            print_cli_dashboard(heads, health_status, selected_head, self.state_manager)

            if not selected_head:
                logger.error("All available heads have been exhausted or failed.")
                raise RuntimeError("No available heads succeeded in generating a response.")

            head_id = selected_head["id"]
            provider_name = selected_head["provider"]
            model_name = selected_head["model"]
            cooldown_sec = selected_head.get("cooldown_seconds", 900)
            readable_selected = head_id.replace("-", " ").title()

            logger.info(f"Router selected head '{head_id}' for execution.")

            start_gen_time = time.time()
            try:
                # Instantiate provider based on config
                if provider_name == "openrouter":
                    provider = OpenRouterProvider(model_name, head_id)
                else:
                    raise ValueError(f"Unknown provider: {provider_name}")
                
                # Execute generation
                response = provider.generate(prompt)
                
                # Success! Record metrics
                gen_latency = int((time.time() - start_gen_time) * 1000)
                self.state_manager.record_success(head_id, latency_ms=gen_latency)
                logger.info(f"Successfully generated response using head '{head_id}'.")
                return response
            except ProviderError as pe:
                # Captured structured diagnostics on provider error
                gen_latency = int((time.time() - start_gen_time) * 1000)
                diagnostics = pe.diagnostics
                diagnostics["latency_ms"] = gen_latency
                
                logger.warning(f"Execution failed on head '{head_id}': {pe}. Falling back...")
                print(f"Execution on {readable_selected} failed! Attempting fallback...\n")
                
                self.state_manager.record_failure(head_id, diagnostics, cooldown_seconds=cooldown_sec)
                health_status[head_id] = diagnostics
                tried_heads.add(head_id)
            except Exception as e:
                gen_latency = int((time.time() - start_gen_time) * 1000)
                diagnostics = {
                    "status": "FAILED",
                    "http_status": None,
                    "latency_ms": gen_latency,
                    "provider": provider_name,
                    "model": model_name,
                    "provider_code": "execution_error",
                    "provider_message": str(e)
                }
                
                logger.warning(f"Execution failed on head '{head_id}': {e}. Falling back...")
                print(f"Execution on {readable_selected} failed! Attempting fallback...\n")
                
                self.state_manager.record_failure(head_id, diagnostics, cooldown_seconds=cooldown_sec)
                health_status[head_id] = diagnostics
                tried_heads.add(head_id)
