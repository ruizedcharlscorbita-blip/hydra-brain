"""
scheduler.py — Hydra Brain v0.6.0
=================================

Dependency-aware TaskGraph scheduler and runner.
Coordinates task lifecycles and dispatches work to registered Specialists.
"""

import logging

from core.context.hydra_context import HydraContext
from core.engines.base import BaseEngine
from core.pipeline.dag import TaskStatus

logger = logging.getLogger("hydra")


class Scheduler(BaseEngine):
    """
    Orchestrates the execution of a TaskGraph, resolving task dependencies
    and executing ready nodes sequentially using dedicated specialists.
    """

    def process(self, context: HydraContext) -> None:
        graph = context.workflow.task_graph
        if not graph:
            logger.warning("Scheduler: no task graph found in context. Skipping execution.")
            return

        from core.specialists import get_specialist

        # Execution loop
        while True:
            ready = graph.get_ready_nodes()
            if not ready:
                # Check for pending nodes that were skipped due to upstream dependency failures
                pending = [n for n in graph.nodes.values() if n.status == TaskStatus.PENDING]
                if pending:
                    logger.warning(
                        f"Scheduler: skipping pending nodes due to incomplete dependencies: "
                        f"{[n.id for n in pending]}"
                    )
                    for n in pending:
                        n.status = TaskStatus.SKIPPED
                break

            for node in ready:
                node.status = TaskStatus.RUNNING
                logger.info(
                    f"Scheduler: executing node {node.id} ({node.name}) "
                    f"using specialist for capability '{node.capability}'"
                )

                # Resolve task specialist
                specialist = get_specialist(node.capability)
                if not specialist:
                    logger.error(f"Scheduler: no specialist found for capability '{node.capability}'")
                    node.status = TaskStatus.FAILED
                    continue

                try:
                    specialist.execute_task(node, context)
                except Exception as e:
                    logger.exception(f"Scheduler: error executing specialist for node {node.id}: {e}")
                    node.status = TaskStatus.FAILED
