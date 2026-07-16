"""
execution_engine.py — Hydra Brain v0.6.0
=========================================

Execution engine mapped to the HydraContext runtime structure.
Supports single-model and concurrent parallel execution models.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed, Future
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from core.context.hydra_context import HydraContext
from core.engines.base import BaseEngine
from core.results.execution_result import ExecutionResult
from providers.openrouter import OpenRouterProvider
from providers.base import ProviderError

logger = logging.getLogger("hydra")

_RETRYABLE_CODES = {"connection_error", "bad_response", "timeout"}
_RETRYABLE_HTTP = {500, 502, 503, 504}


def _is_retryable(result: ExecutionResult) -> bool:
    if result.success:
        return False
    if result.error_code in _RETRYABLE_CODES:
        return True
    if result.http_status in _RETRYABLE_HTTP:
        return True
    return False


def _build_synthetic_head_id(model_id: str) -> str:
    return model_id.replace("/", "-").replace(":", "-").replace(".", "-")


class SingleModelExecutor:
    """Dispatches a prompt to a single registry model with retry/timeout logic."""

    def __init__(
        self,
        timeout_seconds: int = 30,
        max_retries: int = 1,
        retry_delay_seconds: float = 0.5,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds

    def execute(
        self,
        prompt: str,
        model: Dict[str, Any],
        routing_score: float = 0.0,
    ) -> ExecutionResult:
        model_id = model.get("model_id", "unknown/model:free")
        provider_name = "openrouter"
        capability_confidence = model.get("capability_confidence", "none")
        head_id = _build_synthetic_head_id(model_id)

        last_result: Optional[ExecutionResult] = None
        total_attempts = 1 + self.max_retries

        for attempt in range(1, total_attempts + 1):
            start_time = time.time()
            logger.debug(
                f"SingleModelExecutor: attempt {attempt}/{total_attempts} "
                f"for model '{model_id}'"
            )

            try:
                provider = OpenRouterProvider(model_id, head_id)
                response_text = provider.generate(prompt)
                latency_ms = int((time.time() - start_time) * 1000)

                result = ExecutionResult.from_success(
                    model_id=model_id,
                    provider=provider_name,
                    response=response_text,
                    latency_ms=latency_ms,
                    http_status=200,
                    routing_score=routing_score,
                    capability_confidence=capability_confidence,
                    attempt=attempt,
                )

                logger.info(
                    f"SingleModelExecutor: success on attempt {attempt} "
                    f"for '{model_id}' ({latency_ms}ms)"
                )
                return result

            except ProviderError as pe:
                latency_ms = int((time.time() - start_time) * 1000)
                diag = pe.diagnostics or {}

                last_result = ExecutionResult.from_failure(
                    model_id=model_id,
                    provider=provider_name,
                    latency_ms=latency_ms,
                    http_status=diag.get("http_status"),
                    error_code=diag.get("provider_code"),
                    error_message=diag.get("provider_message") or str(pe),
                    routing_score=routing_score,
                    capability_confidence=capability_confidence,
                    attempt=attempt,
                )

                logger.warning(
                    f"SingleModelExecutor: ProviderError on attempt {attempt} "
                    f"for '{model_id}': {pe} (http={diag.get('http_status')})"
                )

                if attempt < total_attempts and _is_retryable(last_result):
                    logger.info(
                        f"SingleModelExecutor: retrying '{model_id}' "
                        f"(retryable error: {last_result.error_code})"
                    )
                    time.sleep(self.retry_delay_seconds)
                    continue
                else:
                    return last_result

            except Exception as e:
                latency_ms = int((time.time() - start_time) * 1000)
                last_result = ExecutionResult.from_failure(
                    model_id=model_id,
                    provider=provider_name,
                    latency_ms=latency_ms,
                    error_code="execution_error",
                    error_message=str(e),
                    routing_score=routing_score,
                    capability_confidence=capability_confidence,
                    attempt=attempt,
                )

                logger.error(
                    f"SingleModelExecutor: unexpected error on attempt {attempt} "
                    f"for '{model_id}': {e}"
                )

                if attempt < total_attempts:
                    time.sleep(self.retry_delay_seconds)
                    continue
                else:
                    return last_result

        return ExecutionResult.from_failure(
            model_id=model_id,
            provider=provider_name,
            latency_ms=0,
            error_code="executor_exhausted",
            error_message="All execution attempts exhausted without result.",
            routing_score=routing_score,
            capability_confidence=capability_confidence,
            attempt=total_attempts,
        )


class ParallelExecutor:
    """Fans out a prompt to multiple models concurrently using a ThreadPool."""

    def __init__(
        self,
        max_workers: int = 4,
        timeout_seconds: int = 30,
        max_retries: int = 0,
    ) -> None:
        self.max_workers = max_workers
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    def execute_all(
        self,
        prompt: str,
        models: List[Dict[str, Any]],
        routing_scores: Optional[Dict[str, float]] = None,
    ) -> List[ExecutionResult]:
        if not models:
            return []

        scores = routing_scores or {}
        executor = SingleModelExecutor(
            timeout_seconds=self.timeout_seconds,
            max_retries=self.max_retries,
        )

        logger.info(
            f"ParallelExecutor: dispatching to {len(models)} models "
            f"(max_workers={self.max_workers})"
        )

        futures: List[Tuple[Future, str]] = []
        results: List[ExecutionResult] = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            for model in models:
                model_id = model.get("model_id", "unknown")
                score = scores.get(model_id, 0.0)
                future = pool.submit(executor.execute, prompt, model, score)
                futures.append((future, model_id))

            for future, model_id in futures:
                try:
                    result = future.result(timeout=self.timeout_seconds + 5)
                    results.append(result)
                except Exception as e:
                    logger.error(
                        f"ParallelExecutor: thread-level error for '{model_id}': {e}"
                    )
                    results.append(ExecutionResult.from_failure(
                        model_id=model_id,
                        provider="openrouter",
                        latency_ms=self.timeout_seconds * 1000,
                        error_code="thread_error",
                        error_message=str(e),
                        routing_score=scores.get(model_id, 0.0),
                    ))

        successful = sorted(
            [r for r in results if r.success],
            key=lambda r: r.latency_ms,
        )
        failed = sorted(
            [r for r in results if not r.success],
            key=lambda r: r.latency_ms,
        )
        return successful + failed

    def execute_top_n(
        self,
        prompt: str,
        ranked_models: List[Tuple[float, Dict[str, Any]]],
        n: int = 3,
    ) -> List[ExecutionResult]:
        top = ranked_models[:n]
        if not top:
            return []

        models = [m for _, m in top]
        routing_scores = {m.get("model_id", ""): score for score, m in top}

        return self.execute_all(
            prompt=prompt,
            models=models,
            routing_scores=routing_scores,
        )


class ExecutionEngine(BaseEngine):
    """
    Envelops single and concurrent parallel model execution.
    Updates context.execution.results in-place.
    """

    def process(self, context: HydraContext) -> None:
        prompt = context.request.prompt
        ranked = context.routing.ranked_models
        settings = context.request.settings

        parallel = settings.get("parallel", False)
        top_n = settings.get("top_n", 1)
        timeout_seconds = settings.get("timeout_seconds", 30)
        max_retries = settings.get("max_retries", 1)

        if parallel and top_n > 1:
            executor = ParallelExecutor(
                max_workers=top_n,
                timeout_seconds=timeout_seconds,
                max_retries=0,
            )
            results = executor.execute_top_n(prompt, ranked, n=top_n)
        else:
            executor = SingleModelExecutor(
                timeout_seconds=timeout_seconds,
                max_retries=max_retries,
            )
            top_score, top_model = ranked[0]
            result = executor.execute(prompt, top_model, routing_score=top_score)
            results = [result]

        context.execution.results = results
