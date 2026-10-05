from __future__ import annotations

from typing import Protocol


class Storage(Protocol):
    """Where original uploads, page images and engine output live.

    Keys are slash-separated relative paths like ``documents/<id>/original.pdf``.
    The local implementation is the default; an S3-compatible one can be added
    behind the same interface without touching the rest of the app.
    """

    def put(self, key: str, data: bytes) -> None: ...

    def get(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...

    def delete_prefix(self, prefix: str) -> None: ...
