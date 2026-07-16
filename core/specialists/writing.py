"""
writing.py — Hydra Brain v0.6.0
==============================

Specialist for copywriting, documentation, and content creation tasks.
"""

from typing import Optional

from core.context.hydra_context import HydraContext
from core.pipeline.dag import TaskNode
from core.specialists.base import BaseSpecialist


class WritingSpecialist(BaseSpecialist):
    """
    Handles copywriting, summarization, drafting, and editing tasks.
    """

    def execute_task(self, node: TaskNode, context: HydraContext, feedback: Optional[str] = None) -> None:
        system_prompt = (
            "You are an expert technical writer and editor. Write clear, "
            "engaging, informative, and grammatically correct text."
        )
        self._execute_with_prompt(node, context, system_prompt, capability="writing", feedback=feedback)
