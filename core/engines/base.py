"""
base.py — Hydra Brain v0.6.0
=============================

Base interface for all Hydra orchestration engines.
"""

from abc import ABC, abstractmethod
from core.context.hydra_context import HydraContext


class BaseEngine(ABC):
    """
    Abstract Base Class representing an engine phase in the pipeline.
    
    Engines process the shared HydraContext in-place.
    """

    @abstractmethod
    def process(self, context: HydraContext) -> None:
        """
        Processes the context. Updates internal states, runs completions,
        or performs checks.
        
        Args:
            context: The shared HydraContext state-carrying object.
        """
        pass
