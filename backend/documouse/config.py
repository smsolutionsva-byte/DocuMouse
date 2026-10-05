"""Runtime configuration, read from environment variables (see .env.example)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

LLM_PRESETS: dict[str, str] = {
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "ollama": "http://localhost:11434/v1",
    "lmstudio": "http://localhost:1234/v1",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DOCUMOUSE_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = "postgresql+psycopg://documouse:documouse@localhost:5432/documouse"
    storage_dir: Path = Path("./data")
    max_upload_mb: int = 25
    max_pages: int = 20
    # Resolution used to turn PDF pages into images for the document engine
    # and the review viewer. 200 DPI keeps small invoice print legible.
    pdf_render_dpi: int = 200

    # Document engine
    engine: Literal["paddle"] = "paddle"
    ocr_lang: str = "en"
    # "fast" swaps in the PP-OCRv5 mobile detection/recognition models (good on CPU);
    # "accurate" uses the PP-StructureV3 defaults (server models).
    ocr_preset: Literal["fast", "accurate"] = "fast"
    ocr_device: str | None = None  # e.g. "cpu", "gpu:0"; None lets Paddle decide
    ocr_detect_orientation: bool = True
    processing_workers: int = 1

    # LLM (optional). Any OpenAI-compatible chat completions endpoint works.
    llm_provider: Literal["none", "openai_compatible", "groq", "openrouter", "ollama", "lmstudio"] = "none"
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_timeout_seconds: float = 60.0

    cors_origins: list[str] = ["http://localhost:3000"]

    @property
    def llm_enabled(self) -> bool:
        return self.llm_provider != "none" and bool(self.llm_model)

    @property
    def resolved_llm_base_url(self) -> str | None:
        return self.llm_base_url or LLM_PRESETS.get(self.llm_provider)


@lru_cache
def get_settings() -> Settings:
    return Settings()
