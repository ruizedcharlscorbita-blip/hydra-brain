"""
correction_engine.py — Hydra Brain v0.6.0
==========================================

Correction engine mapped to the HydraContext runtime structure.
Implements the self-correction loop, retrying candidate models sequentially
until one passes verification constraints.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from core.context.hydra_context import HydraContext
from core.engines.base import BaseEngine
from core.engines.execution_engine import SingleModelExecutor
from core.engines.consensus_engine import ConsensusEngine
from core.engines.verification_engine import VerificationEngine
from core.results.execution_result import ExecutionResult
from core.results.consensus_result import ConsensusResult
from core.results.verification_result import VerificationResult
from core.results.correction_result import CorrectionResult

logger = logging.getLogger("hydra")


class SelfCorrectionLoop:
    """
    Tries candidate models sequentially in ranked order until one produces
    a response that passes all verification checks, or max_attempts is reached.
    """
    def __init__(
        self,
        verifier: VerificationEngine,
        max_attempts: int = 3,
        timeout_seconds: int = 30,
    ):
        self.verifier = verifier
        self.max_attempts = max_attempts
        self.timeout_seconds = timeout_seconds

    def run(
        self,
        prompt: str,
        ranked_models: List[Tuple[float, Dict[str, Any]]],
        strategy: str = "scored",
    ) -> CorrectionResult:
        if not ranked_models:
            raise ValueError("SelfCorrectionLoop: ranked_models list is empty.")

        attempt_log: List[Dict[str, Any]] = []
        executor = SingleModelExecutor(timeout_seconds=self.timeout_seconds, max_retries=0)
        consensus_engine = ConsensusEngine()

        best_attempt_res: Optional[Tuple[ConsensusResult, VerificationResult]] = None
        best_ver_score = -1.0

        candidates_to_try = ranked_models[:self.max_attempts]
        logger.info(f"SelfCorrectionLoop: starting loop over up to {len(candidates_to_try)} candidates.")

        for i, (routing_score, model) in enumerate(candidates_to_try, start=1):
            model_id = model.get("model_id", "unknown")
            logger.info(f"SelfCorrectionLoop: Attempt {i}/{len(candidates_to_try)} using '{model_id}'")

            exec_result = executor.execute(prompt, model, routing_score=routing_score)
            ver_result = self.verifier.verify(exec_result, self.verifier.constraints or [])
            consensus_res = consensus_engine.evaluate([exec_result], strategy=strategy)

            attempt_info = {
                "attempt": i,
                "model_id": model_id,
                "execution_success": exec_result.success,
                "verification_passed": ver_result.passed,
                "verification_score": ver_result.score,
                "latency_ms": exec_result.latency_ms
            }
            attempt_log.append(attempt_info)

            is_better = False
            if best_attempt_res is None:
                is_better = True
            else:
                current_ver_score = ver_result.score
                if current_ver_score > best_ver_score:
                    is_better = True
                elif current_ver_score == best_ver_score:
                    prev_routing_score = best_attempt_res[0].winner.routing_score
                    if routing_score > prev_routing_score:
                        is_better = True

            if is_better:
                best_attempt_res = (consensus_res, ver_result)
                best_ver_score = ver_result.score

            if ver_result.passed:
                logger.info(f"SelfCorrectionLoop: Success! Model '{model_id}' passed verification.")
                return CorrectionResult(
                    final_consensus=consensus_res,
                    final_verification=ver_result,
                    passed=True,
                    attempts=i,
                    attempt_log=attempt_log
                )

            logger.warning(
                f"SelfCorrectionLoop: Model '{model_id}' failed verification. "
                f"Score: {ver_result.score:.4f}"
            )

        logger.warning("SelfCorrectionLoop: All correction attempts exhausted without a passing response.")
        assert best_attempt_res is not None
        final_consensus, final_verification = best_attempt_res

        return CorrectionResult(
            final_consensus=final_consensus,
            final_verification=final_verification,
            passed=False,
            attempts=len(candidates_to_try),
            attempt_log=attempt_log
        )


class CorrectionEngine(BaseEngine):
    """
    Orchestrates the self-correction loop using SelfCorrectionLoop.
    Updates context.execution in-place.
    """

    def process(self, context: HydraContext) -> None:
        prompt = context.request.prompt
        ranked = context.routing.ranked_models
        settings = context.request.settings

        max_correction_attempts = settings.get("max_correction_attempts", 3)
        timeout_seconds = settings.get("timeout_seconds", 30)
        consensus_strategy = settings.get("consensus_strategy", "scored")

        # Reuse verifier configured with constraints
        verifier = VerificationEngine(context.request.constraints)

        loop = SelfCorrectionLoop(
            verifier=verifier,
            max_attempts=max_correction_attempts,
            timeout_seconds=timeout_seconds
        )
        corr_result = loop.run(prompt, ranked, strategy=consensus_strategy)

        context.execution.consensus = corr_result.final_consensus
        context.execution.verification = corr_result.final_verification
        context.execution.correction = corr_result
