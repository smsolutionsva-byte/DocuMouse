from __future__ import annotations

from functools import lru_cache

from ...config import get_settings
from .base import DocumentEngine, EngineResult, EngineUnavailable


@lru_cache
def get_engine() -> DocumentEngine:
    settings = get_settings()
    if settings.engine == "paddle":
        from .paddle import PaddleStructureEngine

        return PaddleStructureEngine(settings)
    raise EngineUnavailable(f"Unknown document engine: {settings.engine}")


__all__ = ["DocumentEngine", "EngineResult", "EngineUnavailable", "get_engine"]
