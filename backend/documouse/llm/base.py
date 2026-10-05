from __future__ import annotations

from typing import Any, Protocol


class LLMError(RuntimeError):
    pass


class LLMProvider(Protocol):
    """Anything that can turn a prompt into a JSON object.

    DocuMouse never lets an LLM write to the database directly: callers validate
    whatever comes back before using it.
    """

    name: str
    model: str

    def complete_json(self, system: str, user: str, *, max_tokens: int = 2000) -> dict[str, Any]: ...
