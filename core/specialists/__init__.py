"""
__init__.py — Hydra Brain v0.6.0
=================================

Initializes the specialist package and registers default capability agents.
"""

from typing import Optional

from core.specialists.base import BaseSpecialist
from core.specialists.registry import SpecialistRegistry
from core.specialists.general import GeneralSpecialist
from core.specialists.coding import CodingSpecialist
from core.specialists.writing import WritingSpecialist
from core.specialists.analysis import AnalysisSpecialist
from core.specialists.reasoning import ReasoningSpecialist
from core.specialists.vision import VisionSpecialist

# Instantiate and configure the global specialist registry
_registry = SpecialistRegistry()
_registry.register("chat", GeneralSpecialist())
_registry.register("coding", CodingSpecialist())
_registry.register("writing", WritingSpecialist())
_registry.register("analysis", AnalysisSpecialist())
_registry.register("reasoning", ReasoningSpecialist())
_registry.register("vision", VisionSpecialist())


def get_specialist(capability: str) -> Optional[BaseSpecialist]:
    """
    Exposes registry query helper. Falls back to 'chat' if capability is unregistered.
    """
    spec = _registry.get(capability)
    if spec is None:
        spec = _registry.get("chat")
    return spec
