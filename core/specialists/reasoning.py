"""
reasoning.py — Hydra Brain v0.6.0
=================================

Specialist for math, logic, and step-by-step reasoning problems.
"""

from typing import Optional

from core.context.hydra_context import HydraContext
from core.pipeline.dag import TaskNode
from core.specialists.base import BaseSpecialist


class ReasoningSpecialist(BaseSpecialist):
    """
    Handles logical problems, mathematics, and step-by-step calculations.
    """

    def execute_task(self, node: TaskNode, context: HydraContext, feedback: Optional[str] = None) -> None:
        system_prompt = (
            "You are an expert logician. Break down problems step-by-step "
            "and explain your logical calculations clearly."
        )
        self._execute_with_prompt(node, context, system_prompt, capability="reasoning", feedback=feedback)
