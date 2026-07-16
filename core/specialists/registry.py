"""
registry.py — Hydra Brain v0.6.0
=================================

Central registry for managing and resolving capability-specific task specialists.
"""

from typing import Dict, Optional

from core.specialists.base import BaseSpecialist


class SpecialistRegistry:
    """
    Registry for cataloging and retrieving specialist implementations
    based on task capability tags.
    """

    def __init__(self) -> None:
        self._specialists: Dict[str, BaseSpecialist] = {}

    def register(self, capability: str, specialist: BaseSpecialist) -> None:
        """
        Registers a specialist instance for a specific capability tag.
        """
        self._specialists[capability] = specialist

    def get(self, capability: str) -> Optional[BaseSpecialist]:
        """
        Resolves a registered specialist for the requested capability tag.
        """
        return self._specialists.get(capability)
