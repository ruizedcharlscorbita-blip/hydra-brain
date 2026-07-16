"""
trace_engine.py — Hydra Brain v0.6.0
=====================================

Observability tracing engine. Compiles trace metadata and seals the final
HydraResult within the HydraContext.
"""

from typing import Any, Dict, List

from core.context.hydra_context import HydraContext
from core.engines.base import BaseEngine
from core.results.trace_result import HydraTrace
from core.results.hydra_result import HydraResult
from core.results.correction_result import CorrectionResult


class TraceEngine(BaseEngine):
    """
    Constructs the end-to-end trace log and compiles the final HydraResult.
    Updates context.trace and context.final_result in-place.
    """

    def process(self, context: HydraContext) -> None:
        exec_ctx = context.execution
        routing_ctx = context.routing
        req_ctx = context.request

        # 1. Determine attempt log
        if exec_ctx.correction:
            attempt_log = exec_ctx.correction.attempt_log
            attempts = exec_ctx.correction.attempts
            passed = exec_ctx.correction.passed
        else:
            attempt_log = []
            results = exec_ctx.results
            attempts = len(results)
            passed = exec_ctx.verification.passed if exec_ctx.verification else False

            # Build attempt log from standard execution results
            for idx, r in enumerate(results):
                is_winner = (exec_ctx.consensus.winner == r) if exec_ctx.consensus else False
                attempt_log.append({
                    "attempt": idx + 1,
                    "model_id": r.model_id,
                    "execution_success": r.success,
                    "verification_passed": passed if is_winner else False,
                    "verification_score": (exec_ctx.verification.score if exec_ctx.verification else 0.0) if is_winner else 0.0,
                    "latency_ms": r.latency_ms
                })

            # Populate CorrectionResult for DAG/Scheduler runs with self_correct=True
            self_correct = req_ctx.settings.get("self_correct", False)
            if self_correct and exec_ctx.consensus and exec_ctx.verification:
                exec_ctx.correction = CorrectionResult(
                    final_consensus=exec_ctx.consensus,
                    final_verification=exec_ctx.verification,
                    passed=passed,
                    attempts=attempts,
                    attempt_log=attempt_log
                )

        # 2. Build HydraTrace
        metadata = {}
        if context.workflow.task_graph:
            metadata["task_graph"] = context.workflow.task_graph.to_dict()

        context.trace = HydraTrace(
            intent=routing_ctx.intent or "chat",
            intent_weights=routing_ctx.intent_weights,
            eligible_models=routing_ctx.eligible_models,
            ranked_models=[(score, model.get("model_id", "unknown")) for score, model in routing_ctx.ranked_models],
            attempt_log=attempt_log,
            metadata=metadata,
        )

        # 3. Compile final HydraResult
        context.final_result = HydraResult(
            response=exec_ctx.consensus.winner.response or "" if exec_ctx.consensus and exec_ctx.consensus.winner else "",
            passed=passed,
            attempts=attempts,
            execution=exec_ctx.consensus.winner if exec_ctx.consensus else None,
            consensus=exec_ctx.consensus,
            verification=exec_ctx.verification,
            confidence=exec_ctx.confidence,
            correction=exec_ctx.correction,
            trace=context.trace,
        )
