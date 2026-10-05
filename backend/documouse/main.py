from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.documents import router as documents_router
from .auth import TokenAuthMiddleware
from .config import get_settings
from .db import create_tables
from .processing import runner

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    runner.resume_pending()
    yield
    runner.shutdown()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="DocuMouse", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(TokenAuthMiddleware)
    app.include_router(documents_router)

    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "engine": settings.engine,
            "ocr_preset": settings.ocr_preset,
            "llm": {
                "enabled": settings.llm_enabled,
                "provider": settings.llm_provider if settings.llm_enabled else None,
                "model": settings.llm_model if settings.llm_enabled else None,
            },
        }

    return app


app = create_app()
