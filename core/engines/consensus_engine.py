"""
consensus_engine.py — Hydra Brain v0.6.0
========================================

Consensus engine mapped to the HydraContext runtime structure.
Selects the winning response from multiple execution results using a specified strategy.
"""

import logging
from typing import List, Optional

from core.context.hydra_context import HydraContext
from core.engines.base import BaseEngine
from core.results.execution_result import ExecutionResult
from core.results.consensus_result import ConsensusResult

logger = logging.getLogger("hydra")

SUPPORTED_STRATEGIES = ("scored", "longest", "fastest")


class ConsensusEngine(BaseEngine):
    """
    Selects the winning model response from execution results.
    Updates context.execution.consensus in-place.
    """

    def process(self, context: HydraContext) -> None:
        results = context.execution.results

        # If task graph is present, prioritize terminal nodes' results
        graph = context.workflow.task_graph
        if graph and graph.nodes:
            terminals = graph.get_terminal_nodes()
            terminal_results = [t.result for t in terminals if t.result is not None]
            if terminal_results:
                results = terminal_results

        strategy = context.request.settings.get("consensus_strategy", "scored")
        context.execution.consensus = self.evaluate(results, strategy)

    def evaluate(
        self,
        results: List[ExecutionResult],
        strategy: str = "scored",
    ) -> ConsensusResult:
        if strategy not in SUPPORTED_STRATEGIES:
            raise ValueError(
                f"Unknown consensus strategy: '{strategy}'. "
                f"Supported: {SUPPORTED_STRATEGIES}"
            )

        successful = [r for r in results if r.success and not r.is_empty_response]
        failed = [r for r in results if not r.success or r.is_empty_response]

        if not successful:
            error_summary = "; ".join(
                f"{r.model_id}({r.error_code})" for r in failed[:5]
            )
            raise RuntimeError(
                f"ConsensusEngine: no successful results to evaluate. "
                f"Failures: [{error_summary}]"
            )

        logger.info(
            f"ConsensusEngine: evaluating {len(successful)} successful results "
            f"using strategy='{strategy}'"
        )

        if strategy == "scored":
            winner, consensus_score = self._strategy_scored(successful)
        elif strategy == "longest":
            winner, consensus_score = self._strategy_longest(successful)
        elif strategy == "fastest":
            winner, consensus_score = self._strategy_fastest(successful)
        else:
            winner, consensus_score = successful[0], 1.0

        logger.info(
            f"ConsensusEngine: selected '{winner.model_id}' "
            f"(strategy={strategy!r}, consensus_score={consensus_score:.4f})"
        )

        return ConsensusResult(
            winner=winner,
            successful=successful,
            failed=failed,
            strategy=strategy,
            consensus_score=consensus_score,
        )

    def _strategy_scored(
        self,
        results: List[ExecutionResult],
    ) -> tuple:
        max_length = max(r.response_length for r in results) or 1
        max_latency = max(r.latency_ms for r in results) or 1

        def score(r: ExecutionResult) -> float:
            s_routing = float(r.routing_score)
            s_length = r.response_length / max_length
            s_speed = 1.0 - (r.latency_ms / max_latency)
            return 0.60 * s_routing + 0.20 * s_length + 0.20 * s_speed

        scored = [(score(r), r) for r in results]
        scored.sort(key=lambda x: x[0], reverse=True)

        winner_score, winner = scored[0]
        max_possible = 1.0
        consensus_score = min(1.0, winner_score / max_possible)

        return winner, consensus_score

    def _strategy_longest(
        self,
        results: List[ExecutionResult],
    ) -> tuple:
        winner = max(results, key=lambda r: r.response_length)
        total_length = sum(r.response_length for r in results) or 1
        consensus_score = winner.response_length / total_length
        return winner, consensus_score

    def _strategy_fastest(
        self,
        results: List[ExecutionResult],
    ) -> tuple:
        winner = min(results, key=lambda r: r.latency_ms)
        max_latency = max(r.latency_ms for r in results) or 1
        consensus_score = 1.0 - (winner.latency_ms / max_latency)
        return winner, consensus_score
