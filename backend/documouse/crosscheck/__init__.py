"""Cross-checking: a second, independent reading of the key fields.

PaddleOCR + the rules produce every value DocuMouse shows. A second reader (PaddleOCR-VL,
or a vision model behind an OpenAI-compatible API) reads the same pages on its own, and
the two readings are compared field by field (business name, date, total):

- they disagree    → the field is flagged, with the second reading as a one-click suggestion
- only the second  → offered as a suggestion, never filled in on its own
  reader found it
- they agree       → recorded; it counts as confirmation (like a total that adds up) only
                     from a reader that picked the value on its own, see compare.py

The second reader never changes a value. It's off unless DOCUMOUSE_SECOND_READER is set.
"""

from __future__ import annotations

from functools import lru_cache

from ..config import get_settings
from .base import KEY_FIELDS, SecondReader, SecondReaderError, SecondReading
from .compare import apply_second_reading, key_values, same_value


@lru_cache
def get_second_reader() -> SecondReader | None:
    settings = get_settings()
    if settings.second_reader == "paddleocr_vl":
        from .paddle_vl import PaddleOCRVLReader

        if not settings.paddleocr_vl_url:
            raise SecondReaderError("Set DOCUMOUSE_PADDLEOCR_VL_URL to use PaddleOCR-VL as the second reader.")
        return PaddleOCRVLReader(url=settings.paddleocr_vl_url, token=settings.paddleocr_vl_token,
                                 model=settings.paddleocr_vl_model, timeout=settings.second_reader_timeout_seconds)
    if settings.second_reader == "vision":
        from .vision import VisionReader

        base_url, model = settings.resolved_vision
        if not base_url or not model:
            raise SecondReaderError("Set DOCUMOUSE_VISION_MODEL (and DOCUMOUSE_VISION_BASE_URL for "
                                    "openai_compatible) to use a vision model as the second reader.")
        if settings.vision_provider in ("gemini", "openrouter", "github") and not settings.vision_api_key:
            raise SecondReaderError(f"Set DOCUMOUSE_VISION_API_KEY to use {settings.vision_provider} as the second reader.")
        return VisionReader(base_url=base_url, model=model, api_key=settings.vision_api_key,
                            timeout=settings.second_reader_timeout_seconds, provider=settings.vision_provider)
    return None


__all__ = [
    "KEY_FIELDS",
    "SecondReader",
    "SecondReaderError",
    "SecondReading",
    "apply_second_reading",
    "get_second_reader",
    "key_values",
    "same_value",
]
