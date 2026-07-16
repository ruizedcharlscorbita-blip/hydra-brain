"""
coding.py — Hydra Brain v0.6.0
==============================

Specialist for coding and software development tasks.
"""

from typing import Optional

from core.context.hydra_context import HydraContext
from core.pipeline.dag import TaskNode
from core.specialists.base import BaseSpecialist
from core.engines.verification_engine import CodeBlockConstraint


class CodingSpecialist(BaseSpecialist):
    """
    Handles coding, scripting, and code review tasks.
    """

    def execute_task(self, node: TaskNode, context: HydraContext, feedback: Optional[str] = None) -> None:
        system_prompt = (
            "You are an expert software engineer. Write clean, well-structured, "
            "correct code in the requested programming language."
        )
        # Default verification includes enforcing code block formatting
        constraints = list(context.request.constraints)
        if not any(isinstance(c, CodeBlockConstraint) for c in constraints):
            constraints.append(CodeBlockConstraint())

        self._execute_with_prompt(
            node,
            context,
            system_prompt,
            capability="coding",
            constraints=constraints,
            feedback=feedback
        )
