"""
pipeline.py — Hydra Brain v0.6.0
=================================

Orchestration pipeline execution manager.
Sequentially runs a series of engines against a shared HydraContext.
"""

import logging
from typing import List

from core.context.hydra_context import HydraContext
from core.engines.base import BaseEngine

logger = logging.getLogger("hydra")


class Pipeline:
    """
    Sequentially executes a series of pipeline steps (BaseEngine instances)
    against a mutable HydraContext.
    """

    def __init__(self, steps: List[BaseEngine]) -> None:
        self.steps = steps

    def run(self, context: HydraContext) -> None:
        for step in self.steps:
            step_name = step.__class__.__name__
            logger.debug(f"Pipeline: running step {step_name}")
            try:
                step.process(context)
            except Exception as e:
                logger.error(f"Pipeline: step {step_name} failed: {e}")
                raise
