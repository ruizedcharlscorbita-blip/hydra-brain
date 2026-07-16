"""
base.py — Hydra Brain v0.6.0
=============================

Abstract base class defining the Specialist interface and common execution behaviors.
"""

from abc import ABC, abstractmethod
import logging
from typing import Any, Dict, List, Optional, Tuple

from core.context.hydra_context import HydraContext
from core.pipeline.dag import TaskNode, TaskStatus
from core.engines.execution_engine import SingleModelExecutor
from core.engines.routing_engine import CapabilityRouter
from core.engines.verification_engine import VerificationEngine
import registry.capability_registry as cap_reg

logger = logging.getLogger("hydra")


class BaseSpecialist(ABC):
    """
    Abstract base class for all capability-specific task execution agents.
    Provides shared routing and execution logic.
    """

    @abstractmethod
    def execute_task(self, node: TaskNode, context: HydraContext, feedback: Optional[str] = None) -> None:
        """
        Executes a single TaskNode, updating the node's result and status in-place.
        Must be implemented by subclasses.
        """
        pass

    def _execute_with_prompt(
        self,
        node: TaskNode,
        context: HydraContext,
        system_prompt: str,
        capability: str,
        constraints: Optional[List[Any]] = None,
        feedback: Optional[str] = None
    ) -> None:
        """
        Helper method that encapsulates routing, prompts, retries, and verification.
        """
        settings = context.request.settings or {}
        timeout = settings.get("timeout_seconds", 30)
        max_retries = settings.get("max_retries", 1)
        self_correct = settings.get("self_correct", False)
        max_attempts = settings.get("max_correction_attempts", 3) if self_correct else 1

        executor = SingleModelExecutor(timeout_seconds=timeout, max_retries=max_retries)
        router = CapabilityRouter()
        
        # Merge specialist constraints with request constraints
        active_constraints = constraints if constraints is not None else context.request.constraints
        verifier = VerificationEngine(constraints=active_constraints)

        # Get eligible models
        eligible_ids = context.routing.eligible_models
        all_models = cap_reg.get_all_models()
        if eligible_ids and all_models:
            models_to_rank = [m for m in all_models if m.get("model_id") in eligible_ids]
        else:
            models_to_rank = all_models if all_models else []

        if not models_to_rank and context.routing.ranked_models:
            models_to_rank = [m for _, m in context.routing.ranked_models]

        # Route models for capability
        intent_weights = {k: 0.0 for k in ["coding", "reasoning", "writing", "analysis", "vision", "chat", "tool_calling", "json_output"]}
        intent_weights[capability] = 1.0

        if context.workflow.task_graph and len(context.workflow.task_graph.nodes) == 1 and context.routing.ranked_models:
            ranked = context.routing.ranked_models
        else:
            ranked = router.rank_models(models_to_rank, intent_weights)

        if not ranked:
            logger.error(f"Specialist: no ranked models found for capability '{capability}'")
            node.status = TaskStatus.FAILED
            return

        # Prepend system prompt to node description
        user_prompt = node.description
        if feedback:
            user_prompt = (
                f"{node.description}\n\n"
                f"### FEEDBACK FROM REVIEWER:\n"
                f"{feedback}\n\n"
                f"Please rewrite your answer to address all issues raised above."
            )
        full_prompt = f"System: {system_prompt}\nUser: {user_prompt}"

        success = False
        for attempt in range(max_attempts):
            if attempt >= len(ranked):
                break
            score, model = ranked[attempt]
            logger.info(f"Specialist: executing node {node.id} attempt {attempt + 1} with model {model.get('model_id')}")

            res = executor.execute(full_prompt, model, routing_score=score)
            node.result = res
            context.execution.results.append(res)

            if res.success:
                if self_correct:
                    ver_res = verifier.verify(res)
                    if ver_res.passed:
                        node.status = TaskStatus.SUCCESS
                        success = True
                        break
                    else:
                        logger.warning(f"Specialist: Node {node.id} failed verification on model {model.get('model_id')}")
                else:
                    node.status = TaskStatus.SUCCESS
                    success = True
                    break
            else:
                logger.warning(f"Specialist: Node {node.id} failed execution on model {model.get('model_id')}")

        if not success:
            node.status = TaskStatus.FAILED
            logger.error(f"Specialist: Node {node.id} failed after all attempts.")
