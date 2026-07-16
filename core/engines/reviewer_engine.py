"""
reviewer_engine.py — Hydra Brain v0.6.0
=======================================

Pipeline engine performing second-pass quality critique and refinement loops.
Audits specialist outputs and requests revisions on quality failures.
"""

import logging
from typing import Optional, Tuple, Dict, Any

from core.context.hydra_context import HydraContext
from core.engines.base import BaseEngine
from core.pipeline.dag import TaskStatus, TaskNode
from core.engines.execution_engine import SingleModelExecutor

logger = logging.getLogger("hydra")


class ReviewerEngine(BaseEngine):
    """
    Evaluates terminal node outputs against domain-specific quality criteria.
    Triggers correction/refinement loops using specialist critique feedback.
    """

    def process(self, context: HydraContext) -> None:
        graph = context.workflow.task_graph
        if not graph:
            logger.debug("ReviewerEngine: no task graph in context. Skipping critique.")
            return

        settings = context.request.settings or {}
        self_correct = settings.get("self_correct", False)
        max_attempts = settings.get("max_correction_attempts", 3) if self_correct else 1

        terminals = graph.get_terminal_nodes()
        executor = SingleModelExecutor(timeout_seconds=30, max_retries=1)

        from core.specialists import get_specialist

        for node in terminals:
            if node.status != TaskStatus.SUCCESS or not node.result:
                continue

            attempts = 1
            while attempts < max_attempts:
                # 1. Generate audit prompt
                audit_prompt, system_prompt = self._build_audit_inputs(node)

                # 2. Query auditor model
                model = self._select_auditor_model(context)
                if not model:
                    logger.warning("ReviewerEngine: no available model to audit. Skipping.")
                    break

                logger.info(f"ReviewerEngine: auditing node {node.id} with model {model.get('model_id')}")

                audit_res = executor.execute(audit_prompt, model)
                if not audit_res.success:
                    logger.warning("ReviewerEngine: audit model completion failed. Skipping critique.")
                    break

                feedback = audit_res.response or ""
                if "APPROVED" in feedback.upper() or "PASS" in feedback.upper():
                    logger.info(f"ReviewerEngine: node {node.id} approved successfully.")
                    break

                # 3. Trigger Specialist Revision
                logger.warning(
                    f"ReviewerEngine: node {node.id} rejected. "
                    f"Triggering specialist revision (attempt {attempts + 1})."
                )

                specialist = get_specialist(node.capability)
                if specialist:
                    node.status = TaskStatus.RUNNING
                    # Re-run task with the reviewer's feedback
                    specialist.execute_task(node, context, feedback=feedback)

                attempts += 1

    def _build_audit_inputs(self, node: TaskNode) -> Tuple[str, str]:
        cap = node.capability
        output = node.result.response if node.result else ""

        system = "You are an expert editor and quality control agent."

        if cap == "coding":
            guidelines = (
                "Audit the code below. Check for:\n"
                "1. Security flaws, basic bugs, or syntax issues.\n"
                "2. Readability and best practices.\n"
                "3. Complexity concerns.\n"
                "Reply with 'APPROVED' if the code is correct and high quality. "
                "Otherwise, list the specific issues and how to fix them."
            )
        elif cap == "writing":
            guidelines = (
                "Audit the text below. Check for:\n"
                "1. Grammar, spelling, and tone consistency.\n"
                "2. Redundancies and flow.\n"
                "Reply with 'APPROVED' if the writing meets professional standards. "
                "Otherwise, suggest stylistic improvements."
            )
        elif cap == "analysis":
            guidelines = (
                "Audit the research analysis below. Check for:\n"
                "1. Unsupported claims or logical contradictions.\n"
                "2. Hallucinations or clear errors.\n"
                "Reply with 'APPROVED' if the analysis is accurate and factual. "
                "Otherwise, list gaps in evidence."
            )
        else:
            guidelines = (
                "Audit the answer below for helpfulness, tone, and accuracy. "
                "Reply with 'APPROVED' if it is high quality. Otherwise, state what to correct."
            )

        prompt = (
            f"System: {system}\n\n"
            f"Prompt: {node.description}\n"
            f"Output:\n{output}\n\n"
            f"{guidelines}"
        )
        return prompt, system

    def _select_auditor_model(self, context: HydraContext) -> Dict[str, Any]:
        if context.routing.ranked_models:
            return context.routing.ranked_models[0][1]
        import registry.capability_registry as cap_reg
        models = cap_reg.get_all_models()
        return models[0] if models else {}
