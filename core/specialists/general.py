"""
general.py — Hydra Brain v0.6.0
================================

General purpose specialist for general assistance tasks.
"""

from typing import Optional

from core.context.hydra_context import HydraContext
from core.pipeline.dag import TaskNode
from core.specialists.base import BaseSpecialist


class GeneralSpecialist(BaseSpecialist):
    """
    Handles general chat or uncategorized tasks.
    """

    def execute_task(self, node: TaskNode, context: HydraContext, feedback: Optional[str] = None) -> None:
        system_prompt = "You are a helpful and concise AI assistant."
        self._execute_with_prompt(node, context, system_prompt, capability="chat", feedback=feedback)
