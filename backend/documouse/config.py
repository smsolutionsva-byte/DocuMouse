"""Runtime configuration, read from environment variables (see .env.example)."""

from __future__ import annotations

import os
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

# Vision providers for the second reader: (OpenAI-compatible base URL, default model).
# Free tiers change often; check the provider's current limits and data terms.
VISION_PRESETS: dict[str, tuple[str, str | None]] = {
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-3.8-flash"),
    "openrouter": ("https://openrouter.ai/api/v1", None),
    "github": ("https://models.github.ai/inference", None),
    "ollama": ("http://localhost:11434/v1", None),
    "lmstudio": ("http://localhost:1234/v1", None),
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DOCUMOUSE_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = "postgresql+psycopg://documouse:documouse@localhost:5432/documouse"
    storage_dir: Path = Path("./data")

    # S3-compatible object store (e.g. Cloudflare R2). When storage_backend is
    # "s3", files go here instead of storage_dir.  R2's free tier covers 10 GB
    # and 10 million class-B operations per month.
    storage_backend: Literal["local", "s3"] = "local"
    s3_endpoint_url: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_bucket: str = "documouse"
    s3_region: str = "auto"

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
    # oneDNN (MKL-DNN) CPU acceleration. None keeps PaddleOCR's default. PaddlePaddle 3.3.x
    # fails with "ConvertPirAttribute2RuntimeAttribute not support" when it's on, see README.
    ocr_enable_mkldnn: bool | None = None
    processing_workers: int = 1

    # LLM (optional). Any OpenAI-compatible chat completions endpoint works.
    llm_provider: Literal["none", "openai_compatible", "groq", "openrouter", "ollama", "lmstudio"] = "none"
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_timeout_seconds: float = 60.0

    # Second reader (optional): reads every page again, independently, so the key fields
    # (business name, date, total) can be cross-checked. See documouse/crosscheck.
    second_reader: Literal["none", "paddleocr_vl", "vision"] = "none"
    # PaddleOCR-VL: an OpenAI-compatible server (llama.cpp's llama-server, vLLM; URL ends in /v1),
    # or a PaddleOCR-VL layout-parsing endpoint (PaddleOCR's hosted API or a PaddleX serving app).
    paddleocr_vl_url: str | None = None
    paddleocr_vl_token: str | None = None  # hosted API only
    paddleocr_vl_model: str = "PaddleOCR-VL-1.6"  # model name sent to an OpenAI-compatible server
    # Vision model behind any OpenAI-compatible chat endpoint.
    vision_provider: Literal["gemini", "openrouter", "github", "ollama", "lmstudio", "openai_compatible"] = "gemini"
    vision_base_url: str | None = None
    vision_api_key: str | None = None
    vision_model: str | None = None
    second_reader_timeout_seconds: float = 180.0

    cors_origins: list[str] = ["http://localhost:3000"]

    # Shared-token authentication. When set, every /api/* request (except
    # /api/health) must carry ``Authorization: Bearer <token>``.
    auth_token: str | None = None

    @property
    def llm_enabled(self) -> bool:
        return self.llm_provider != "none" and bool(self.llm_model)

    @property
    def resolved_llm_base_url(self) -> str | None:
        return self.llm_base_url or LLM_PRESETS.get(self.llm_provider)

    @property
    def resolved_vision(self) -> tuple[str | None, str | None]:
        """(base URL, model) for the vision second reader, with the provider's defaults filled in."""
        base_url, model = VISION_PRESETS.get(self.vision_provider, (None, None))
        return self.vision_base_url or base_url, self.vision_model or model


def _export_paddle_env(env_file: Path = Path(".env")) -> None:
    """PaddleX reads PADDLE_PDX_* from the process environment, so pass those through from .env."""
    if not env_file.is_file():
        return
    for line in env_file.read_text().splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key.startswith("PADDLE_") and key not in os.environ:
            os.environ[key] = value.strip().strip("\"'")


@lru_cache
def get_settings() -> Settings:
    _export_paddle_env()
    return Settings()
