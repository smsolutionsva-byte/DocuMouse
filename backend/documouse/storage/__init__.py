from __future__ import annotations

from functools import lru_cache

from ..config import get_settings
from .base import Storage
from .local import LocalStorage


@lru_cache
def get_storage() -> Storage:
    settings = get_settings()
    if settings.storage_backend == "s3":
        from .s3 import S3Storage

        return S3Storage(
            bucket=settings.s3_bucket,
            endpoint_url=settings.s3_endpoint_url,
            region=settings.s3_region,
            access_key_id=settings.s3_access_key_id or "",
            secret_access_key=settings.s3_secret_access_key or "",
        )
    return LocalStorage(settings.storage_dir)


__all__ = ["Storage", "LocalStorage", "get_storage"]

