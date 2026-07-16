"""
vision.py — Hydra Brain v0.6.0
==============================

Specialist for visual analysis, description, and image understanding tasks.
"""

from typing import Optional

from core.context.hydra_context import HydraContext
from core.pipeline.dag import TaskNode
from core.specialists.base import BaseSpecialist


class VisionSpecialist(BaseSpecialist):
    """
    Handles image description and visual query tasks.
    """

    def execute_task(self, node: TaskNode, context: HydraContext, feedback: Optional[str] = None) -> None:
        system_prompt = (
            "You are an expert computer vision model. Analyze visual details "
            "and describe elements carefully."
        )
        self._execute_with_prompt(node, context, system_prompt, capability="vision", feedback=feedback)
