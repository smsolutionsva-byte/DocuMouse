from __future__ import annotations

import io
import os

import pytest
from PIL import Image

from documouse.processing.engines.base import EngineResult

from .fixtures import invoice_raw, receipt_raw


class FakeEngine:
    """Test double standing in for PP-StructureV3 (whose models aren't downloaded in CI)."""

    name = "test-double"

    def __init__(self, raw_factory):
        self.raw_factory = raw_factory

    def process(self, pages):
        raw = self.raw_factory()
        return EngineResult(document=raw)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # Set DOCUMOUSE_TEST_DATABASE_URL to run the API tests against PostgreSQL.
    db_url = os.environ.get("DOCUMOUSE_TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setenv("DOCUMOUSE_DATABASE_URL", db_url)
    monkeypatch.setenv("DOCUMOUSE_STORAGE_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DOCUMOUSE_LLM_PROVIDER", "none")
    monkeypatch.setenv("DOCUMOUSE_SECOND_READER", "none")

    from documouse import config, crosscheck, db, llm, storage
    from documouse.processing import engines, pipeline, runner

    config.get_settings.cache_clear()
    storage.get_storage.cache_clear()
    llm.get_llm.cache_clear()
    crosscheck.get_second_reader.cache_clear()
    engines.get_engine.cache_clear()
    db.init_engine()

    engine_box = {"factory": invoice_raw}
    monkeypatch.setattr(pipeline, "get_engine", lambda: FakeEngine(lambda: engine_box["factory"]()))
    monkeypatch.setattr(runner, "enqueue", lambda doc_id: pipeline.process_document(doc_id))

    from fastapi.testclient import TestClient

    from documouse.main import create_app

    with TestClient(create_app()) as c:
        c.engine_box = engine_box  # type: ignore[attr-defined]
        c.use_receipt = lambda: engine_box.update(factory=receipt_raw)  # type: ignore[attr-defined]
        yield c
    db.Base.metadata.drop_all(db.get_engine())


def png_bytes(color=(255, 255, 255), size=(827, 1169)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()
