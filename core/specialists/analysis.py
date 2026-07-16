"""
analysis.py — Hydra Brain v0.6.0
================================

Specialist for data analysis and research comparison tasks.
"""

from typing import Optional

from core.context.hydra_context import HydraContext
from core.pipeline.dag import TaskNode
from core.specialists.base import BaseSpecialist


class AnalysisSpecialist(BaseSpecialist):
    """
    Handles analytical queries, research comparisons, and data inspection tasks.
    """

    def execute_task(self, node: TaskNode, context: HydraContext, feedback: Optional[str] = None) -> None:
        system_prompt = (
            "You are an expert research analyst. Perform deep research, "
            "inspect details carefully, and provide clear comparative analysis."
        )
        self._execute_with_prompt(node, context, system_prompt, capability="analysis", feedback=feedback)
