from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from PIL import Image

from ..pages import PageImage
from ..types import RawDocument


class EngineUnavailable(RuntimeError):
    """The engine can't run here (not installed, models unreachable, ...)."""


@dataclass
class EngineResult:
    document: RawDocument
    # Some engines straighten rotated pages; when they do, the corrected image
    # replaces the original page image so coordinates still line up in the viewer.
    corrected_pages: dict[int, Image.Image] = field(default_factory=dict)
    # Native engine output per page, kept for debugging and re-processing.
    native: list[dict[str, Any]] = field(default_factory=list)


class DocumentEngine(Protocol):
    name: str

    def process(self, pages: list[PageImage]) -> EngineResult: ...
