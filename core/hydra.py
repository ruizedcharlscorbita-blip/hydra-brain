import logging
import time
from datetime import datetime
from typing import Dict, Any, List, Optional
from core.registry import HeadRegistry
from core.health import HealthChecker
from core.router import Router
from core.state import StateManager
from core.context.hydra_context import HydraContext, RequestContext
from core.pipeline.pipeline import Pipeline
from core.results.hydra_result import HydraResult
from core.results.execution_result import ExecutionResult
from core.results.consensus_result import ConsensusResult
from core.results.verification_result import VerificationResult
from core.results.correction_result import CorrectionResult
from core.results.confidence_result import ConfidenceScore
from core.results.trace_result import HydraTrace
from core.engines.intent_engine import IntentEngine
from core.engines.routing_engine import RoutingEngine
from core.engines.execution_engine import ExecutionEngine
from core.engines.consensus_engine import ConsensusEngine
from core.engines.verification_engine import VerificationEngine, NonEmptyConstraint
from core.engines.correction_engine import CorrectionEngine
from core.engines.confidence_engine import ConfidenceEngine
from core.engines.trace_engine import TraceEngine
from core.engines.reviewer_engine import ReviewerEngine
from core.pipeline.planner import PlannerEngine
from core.pipeline.scheduler import Scheduler
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
        
        # Sprint 6.1: Context-driven Engines
        self.intent_engine = IntentEngine()
        self.routing_engine = RoutingEngine()
        self.execution_engine = ExecutionEngine()
        self.consensus_engine = ConsensusEngine()
        self.verification_engine = VerificationEngine()
        self.correction_engine = CorrectionEngine()
        self.confidence_engine = ConfidenceEngine()
        self.trace_engine = TraceEngine()
        self.planner_engine = PlannerEngine()
        self.scheduler = Scheduler()
        self.reviewer_engine = ReviewerEngine()

        # Legacy backward compatibility mappings
        self.intent_parser = self.intent_engine
        self.capability_router = self.routing_engine.router
        self.policy = self.routing_engine.policy

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

    def route_by_capability(self, prompt: str, top_n: int = 5) -> Dict[str, Any]:
        """
        Capability-aware routing path (Sprint 3).

        Runs the full pipeline:
            1. Parse intent from prompt  → capability weight dict
            2. Load registry models      → full enriched model list
            3. Apply policy filter       → eligible candidates only
            4. Score & rank candidates   → composite score per model
            5. Return routing result     → selected model + metadata

        Does NOT execute a generation request. Returns a routing decision
        that the caller can use to dispatch to the chosen model.

        Args:
            prompt: The user query string.
            top_n: How many ranked candidates to include in the result.

        Returns:
            Dict with keys:
                "prompt"        : original prompt string
                "intent"        : Dict[str, float] — parsed capability weights
                "dominant"      : str — the highest-weight capability
                "candidates"    : List[Tuple[float, model_id_str]] — top_n ranked
                "selected_model": Dict — the top-ranked model (or None)
                "score"         : float — composite score of selected model
                "eligible_count": int — number of models that passed policy gate
                "total_count"   : int — total models in registry
        """
        import registry.capability_registry as cap_reg

        logger.info(f"route_by_capability called for prompt: '{prompt[:80]}'")

        # Step 1: Parse intent
        intent_weights = self.intent_parser.parse_intent(prompt)
        dominant = self.intent_parser.dominant_capability(prompt)
        logger.info(f"Intent parsed: dominant='{dominant}', weights={intent_weights}")

        # Step 2: Load all models from the enriched registry
        all_models = cap_reg.get_all_models()
        total_count = len(all_models)

        # Step 3: Apply policy filter
        eligible = self.policy.filter_candidates(all_models)
        eligible_count = len(eligible)
        logger.info(f"Policy filter: {eligible_count}/{total_count} models eligible")

        # Step 4: Score and rank
        ranked = self.capability_router.rank_models(eligible, intent_weights)

        # Step 5: Build result
        selected_model = ranked[0][1] if ranked else None
        top_score = ranked[0][0] if ranked else 0.0

        candidates = [
            (score, m.get("model_id", "unknown"))
            for score, m in ranked[:top_n]
        ]

        result = {
            "prompt": prompt,
            "intent": intent_weights,
            "dominant": dominant,
            "candidates": candidates,
            "selected_model": selected_model,
            "score": round(top_score, 6),
            "eligible_count": eligible_count,
            "total_count": total_count,
        }

        if selected_model:
            logger.info(
                f"Routing decision: '{selected_model.get('model_id')}' "
                f"(score={top_score:.4f}, confidence={selected_model.get('capability_confidence')})"
            )
        else:
            logger.warning("route_by_capability: no eligible model found.")

        return result

    def execute_with_capability(
        self,
        prompt: str,
        parallel: bool = False,
        top_n: int = 1,
        consensus_strategy: str = "scored",
        timeout_seconds: int = 30,
        max_retries: int = 1,
    ) -> ConsensusResult:
        """
        Full capability-aware execution pipeline (Sprint 4).

        Combines routing (Sprint 3) with execution and consensus (Sprint 4)
        into a single call. Returns a structured ConsensusResult rather than
        a raw string.

        Pipeline:
            1. Parse intent from prompt     → capability weight dict
            2. Load registry models         → full enriched model list
            3. Apply policy filter          → eligible candidates only
            4. Rank by capability score     → ordered candidate list
            5. Execute: single or parallel  → ExecutionResult(s)
            6. Consensus                    → select winner
            7. Return ConsensusResult

        Args:
            prompt: The user query string.
            parallel: If True, dispatches to top_n models concurrently.
                      If False, executes the single highest-ranked model.
            top_n: Number of models to use. Only meaningful when parallel=True.
                   Ignored (treated as 1) in single-model mode.
            consensus_strategy: "scored", "longest", or "fastest".
            timeout_seconds: Per-model execution timeout.
            max_retries: Retry attempts on transient failures.

        Returns:
            ConsensusResult — winner + successful + failed lists + metadata.

        Raises:
            RuntimeError: If no eligible models exist or all executions fail.
        """
        import registry.capability_registry as cap_reg

        logger.info(
            f"execute_with_capability: prompt='{prompt[:80]}' "
            f"parallel={parallel}, top_n={top_n}, strategy={consensus_strategy!r}"
        )

        # Step 1: Parse intent
        intent_weights = self.intent_parser.parse_intent(prompt)
        dominant = self.intent_parser.dominant_capability(prompt)
        logger.info(f"Intent: dominant='{dominant}', weights={intent_weights}")

        # Step 2: Load registry models
        all_models = cap_reg.get_all_models()
        if not all_models:
            raise RuntimeError("execute_with_capability: registry is empty.")

        # Step 3: Apply policy filter
        eligible = self.policy.filter_candidates(all_models)
        if not eligible:
            raise RuntimeError(
                "execute_with_capability: no eligible models after policy filter."
            )

        # Step 4: Rank by capability
        ranked = self.capability_router.rank_models(eligible, intent_weights)
        if not ranked:
            raise RuntimeError(
                "execute_with_capability: ranking produced no results."
            )

        # Step 5: Execute
        if parallel and top_n > 1:
            executor = ParallelExecutor(
                max_workers=top_n,
                timeout_seconds=timeout_seconds,
                max_retries=0,  # No retries in parallel mode to keep latency low
            )
            results = executor.execute_top_n(prompt, ranked, n=top_n)
        else:
            # Single best model
            engine = ExecutionEngine(
                timeout_seconds=timeout_seconds,
                max_retries=max_retries,
            )
            top_score, top_model = ranked[0]
            result = engine.execute(prompt, top_model, routing_score=top_score)
            results = [result]

        # Step 6: Consensus
        consensus_engine = ConsensusEngine()
        consensus = consensus_engine.evaluate(results, strategy=consensus_strategy)

        logger.info(
            f"execute_with_capability: winner='{consensus.winner.model_id}' "
            f"(strategy={consensus_strategy!r}, "
            f"consensus_score={consensus.consensus_score:.4f}, "
            f"{consensus.successful_count}/{consensus.total_count} succeeded)"
        )

        return consensus

    def execute_and_verify(
        self,
        prompt: str,
        constraints: Optional[List[Any]] = None,
        parallel: bool = False,
        top_n: int = 1,
        consensus_strategy: str = "scored",
        self_correct: bool = True,
        max_correction_attempts: int = 3,
        timeout_seconds: int = 30,
        max_retries: int = 1,
    ) -> HydraResult:
        """
        Executes a prompt, runs validation constraints, and optionally applies
        self-correction loop (Sprint 5).

        Pipeline:
            1. Intent parse & capability routing
            2. Run verification constraints (defaulting to NonEmptyConstraint)
            3. If self_correct=True, execute via SelfCorrectionLoop (serial fallback)
            4. Otherwise, execute normal path (single or parallel) & verify result
            5. Run ConfidenceScorer
            6. Return HydraResult

        Args:
            prompt: User prompt query.
            constraints: List of constraint objects. Default is [NonEmptyConstraint()].
            parallel: If True and self_correct=False, dispatches to top_n models in parallel.
            top_n: How many top models to execute (ignored if parallel=False).
            consensus_strategy: Strategy to select the consensus winner.
            self_correct: Whether to retry alternative models on verification failure.
            max_correction_attempts: Maximum attempts for self-correction.
            timeout_seconds: Time budget per invocation.
            max_retries: Retry attempts on transient errors.

        Returns:
            HydraResult — containing response, passed status, consensus, verification,
            confidence score, and correction details.

        Raises:
            RuntimeError: If no eligible models exist or all executions fail.
        """
        # 1. Initialize Context
        active_constraints = constraints if constraints is not None else [NonEmptyConstraint()]
        req = RequestContext(
            prompt=prompt,
            constraints=active_constraints,
            settings={
                "parallel": parallel,
                "top_n": top_n,
                "consensus_strategy": consensus_strategy,
                "self_correct": self_correct,
                "max_correction_attempts": max_correction_attempts,
                "timeout_seconds": timeout_seconds,
                "max_retries": max_retries
            }
        )
        context = HydraContext(request=req)

        # 2. Assemble and run the pipeline
        steps = [
            self.intent_engine,
            self.routing_engine,
            self.planner_engine,
            self.scheduler,
            self.reviewer_engine,
            self.consensus_engine,
            self.verification_engine,
            self.confidence_engine,
            self.trace_engine,
        ]

        pipeline = Pipeline(steps)
        pipeline.run(context)

        return context.final_result

