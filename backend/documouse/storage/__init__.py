from __future__ import annotations

from functools import lru_cache

from ..config import get_settings
from .base import Storage
from .local import LocalStorage


@lru_cache
def get_storage() -> Storage:
    return LocalStorage(get_settings().storage_dir)


__all__ = ["Storage", "LocalStorage", "get_storage"]
