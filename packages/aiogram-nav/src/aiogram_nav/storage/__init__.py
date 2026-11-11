"""Navigation storage contracts; optional Redis is selected via storage.redis."""

from .base import NavigationRepository
from .memory import MemoryNavigationRepository

__all__ = ["NavigationRepository", "MemoryNavigationRepository"]
