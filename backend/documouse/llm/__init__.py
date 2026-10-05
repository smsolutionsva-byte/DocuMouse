from __future__ import annotations

from functools import lru_cache

from ..config import get_settings
from .base import LLMError, LLMProvider
from .openai_compat import OpenAICompatibleProvider


@lru_cache
def get_llm() -> LLMProvider | None:
    """The configured provider, or None when DocuMouse runs without an LLM."""
    settings = get_settings()
    if not settings.llm_enabled:
        return None
    base_url = settings.resolved_llm_base_url
    if not base_url:
        raise LLMError("DOCUMOUSE_LLM_BASE_URL is required for the openai_compatible provider.")
    return OpenAICompatibleProvider(
        name=settings.llm_provider,
        base_url=base_url,
        model=settings.llm_model or "",
        api_key=settings.llm_api_key,
        timeout=settings.llm_timeout_seconds,
    )


__all__ = ["LLMError", "LLMProvider", "OpenAICompatibleProvider", "get_llm"]
