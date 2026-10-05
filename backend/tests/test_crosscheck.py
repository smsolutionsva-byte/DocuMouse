import json
from datetime import date

import httpx
import pytest

from documouse.crosscheck import SecondReading, apply_second_reading, key_values
from documouse.crosscheck.paddle_vl import PaddleOCRVLReader, parse_spotting
from documouse.crosscheck.vision import VisionReader
from documouse.processing.pages import PageImage
from documouse.understanding.extract import extract
from documouse.validation import validate

from .conftest import png_bytes
from .fixtures import receipt_raw

TODAY = date(2026, 10, 6)


def reading(**values) -> SecondReading:
    return SecondReading(reader="Second reader", values=values)


def status(data, key):
    return validate(data, today=TODAY).fields[key]


def test_agreement_confirms_a_value_the_rules_were_unsure_about():
    data = extract(receipt_raw(), "receipt")
    data.fields["merchant"].confidence = 0.5
    data.fields["merchant"].notes = []
    assert status(data, "merchant")["status"] == "review"

    # Punctuation and spacing don't count as a difference.
    checked = apply_second_reading(data, reading(name="Corner  Cafe.", date="2026-10-03", total="11.70"))
    for key in ("merchant", "date", "total"):
        assert checked.fields[key].second_opinion.confirms, key
    assert status(checked, "merchant")["status"] == "verified"
    assert checked.fields["merchant"].value == "CORNER CAFE"


def test_disagreement_flags_and_suggests_but_never_overwrites():
    data = extract(receipt_raw(), "receipt")
    assert status(data, "total")["status"] == "verified"

    checked = apply_second_reading(data, reading(name="CORNER CAFE", date="2026-10-03", total="11.10"))
    total = checked.fields["total"]
    assert total.value == "11.70"
    assert total.suggestion.value == "11.10"
    assert not total.second_opinion.agrees
    s = status(checked, "total")
    assert s["status"] == "review"
    assert "disagrees" in s["reasons"][0]


def test_a_value_only_the_second_reader_found_is_only_suggested():
    data = extract(receipt_raw(), "receipt")
    data.fields["date"] = data.fields["date"].model_copy(update={"value": None, "raw": None})
    checked = apply_second_reading(data, reading(date="2026-10-03"))
    assert checked.fields["date"].value is None
    assert checked.fields["date"].suggestion.value == "2026-10-03"
    assert status(checked, "date")["status"] == "missing"


def test_nothing_found_by_the_second_reader_changes_nothing():
    data = extract(receipt_raw(), "receipt")
    checked = apply_second_reading(data, reading(name=None, date=None, total=None))
    for key in ("merchant", "date", "total"):
        assert status(checked, key) == status(data, key)


def test_values_a_person_decided_are_left_alone():
    data = extract(receipt_raw(), "receipt")
    data.fields["total"].confirmed = True
    checked = apply_second_reading(data, reading(total="99.00"))
    assert checked.fields["total"].suggestion is None
    assert checked.fields["total"].second_opinion is None


def test_an_ocr_style_reading_goes_through_the_same_rules():
    raw = receipt_raw()
    raw.lines[0].text = "C0RNER CAFE"  # the second reader misread one character
    second = SecondReading(reader="PaddleOCR-VL", raw=raw)
    assert key_values(second, "receipt") == {"merchant": "C0RNER CAFE", "date": "2026-10-03", "total": "11.70"}
    data = extract(receipt_raw(), "receipt")
    data.fields["date"].confidence = 0.5
    checked = apply_second_reading(data, second)
    assert not checked.fields["merchant"].second_opinion.agrees
    assert status(checked, "merchant")["status"] == "review"
    # Same rules on both readings: agreeing only shows the characters match, so it doesn't confirm.
    assert checked.fields["date"].second_opinion.agrees
    assert not checked.fields["date"].second_opinion.confirms
    assert status(checked, "date")["status"] == "review"


def test_parse_spotting_output():
    out = ("BOOK TA K SDN BHD<|LOC_160|><|LOC_310|><|LOC_900|><|LOC_310|><|LOC_900|><|LOC_374|><|LOC_160|><|LOC_374|>\n"
           "<|TEXT_START|>57 &amp; 59 JALAN<|TEXT_END|><|LOC_BEGIN|><|LOC_242|><|LOC_482|><|LOC_820|><|LOC_482|>"
           "<|LOC_820|><|LOC_544|><|LOC_242|><|LOC_544|><|LOC_END|></s>")
    assert parse_spotting(out) == [
        ("BOOK TA K SDN BHD", (0.16, 0.31, 0.9, 0.374)),
        ("57 & 59 JALAN", (0.242, 0.482, 0.82, 0.544)),
    ]


def _page():
    from PIL import Image
    import io

    return PageImage(index=0, image=Image.open(io.BytesIO(png_bytes(size=(400, 800)))).convert("RGB"))


def _reply(content):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]},
                          request=httpx.Request("POST", "http://x"))


def test_paddleocr_vl_over_an_openai_compatible_server(monkeypatch):
    sent = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        sent.update(url=url, payload=json)
        return _reply("TOTAL 11.70<|LOC_100|><|LOC_500|><|LOC_900|><|LOC_500|><|LOC_900|><|LOC_520|><|LOC_100|><|LOC_520|>")

    monkeypatch.setattr(httpx, "post", fake_post)
    reader = PaddleOCRVLReader(url="http://127.0.0.1:8080/v1", token=None, model="PaddleOCR-VL-1.6", timeout=5)
    result = reader.read([_page()], "receipt")
    assert sent["url"] == "http://127.0.0.1:8080/v1/chat/completions"
    assert sent["payload"]["skip_special_tokens"] is False
    assert sent["payload"]["messages"][0]["content"][1] == {"type": "text", "text": "Spotting:"}
    assert [(ln.text, ln.bbox) for ln in result.raw.lines] == [("TOTAL 11.70", [0.1, 0.5, 0.9, 0.52])]


def test_paddleocr_vl_over_the_layout_parsing_api(monkeypatch):
    sent = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        sent.update(url=url, body=json, headers=headers)
        spotting = {"rec_texts": ["TOTAL 11.70"], "rec_polys": [[[40, 400], [360, 400], [360, 416], [40, 416]]]}
        return httpx.Response(200, request=httpx.Request("POST", url), json={
            "errorCode": 0,
            "result": {"layoutParsingResults": [{"prunedResult": {"width": 400, "height": 800, "spotting_res": spotting}}]},
        })

    monkeypatch.setattr(httpx, "post", fake_post)
    reader = PaddleOCRVLReader(url="https://example.test/layout-parsing", token="secret", model="", timeout=5)
    result = reader.read([_page()], "receipt")
    assert sent["headers"]["Authorization"] == "token secret"
    assert sent["body"]["promptLabel"] == "spotting" and sent["body"]["useLayoutDetection"] is False
    assert [(ln.text, ln.bbox) for ln in result.raw.lines] == [("TOTAL 11.70", [0.1, 0.5, 0.9, 0.52])]


def test_vision_reader_sends_the_page_and_reads_json(monkeypatch):
    sent = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        sent.update(url=url, headers=headers, payload=json)
        return _reply('```json\n{"name": "CORNER CAFE", "date": "2026-10-03", "total": "11.70"}\n```')

    monkeypatch.setattr(httpx, "post", fake_post)
    reader = VisionReader(base_url="https://generativelanguage.googleapis.com/v1beta/openai", model="gemini-3.8-flash",
                          api_key="key", timeout=5, provider="gemini")
    result = reader.read([_page()], "receipt")
    content = sent["payload"]["messages"][1]["content"]
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert sent["headers"]["Authorization"] == "Bearer key"
    assert result.reader == "gemini-3.8-flash"
    assert key_values(result, "receipt") == {"merchant": "CORNER CAFE", "date": "2026-10-03", "total": "11.70"}


class FakeReader:
    name = "Fake reader"

    def __init__(self, fail=False):
        self.fail = fail

    def read(self, pages, doc_type):
        if self.fail:
            raise RuntimeError("server unreachable")
        return SecondReading(reader=self.name, values={"name": "CORNER CAFE", "date": "2026-10-03", "total": "11.10"})


@pytest.mark.parametrize("fail", [False, True])
def test_pipeline_cross_checks_and_survives_a_failing_reader(client, monkeypatch, fail):
    from documouse.processing import pipeline

    monkeypatch.setattr(pipeline, "get_second_reader", lambda: FakeReader(fail=fail))
    client.use_receipt()
    r = client.post("/api/documents", files={"file": ("r.png", png_bytes(), "image/png")})
    doc = client.get(f"/api/documents/{r.json()['id']}").json()
    assert doc["status"] == "ready", doc.get("error_detail")
    total = doc["data"]["fields"]["total"]
    assert total["value"] == "11.70"
    if fail:
        assert total["second_opinion"] is None
        return
    assert total["second_opinion"] == {"reader": "Fake reader", "value": "11.10", "agrees": False, "confirms": False}
    assert doc["validation"]["fields"]["total"]["status"] == "review"
    assert doc["data"]["fields"]["merchant"]["second_opinion"]["agrees"]

    # Changing the type re-uses the stored second reading instead of reading again.
    monkeypatch.setattr(pipeline, "get_second_reader", lambda: FakeReader(fail=True))
    doc = client.post(f"/api/documents/{doc['id']}/type", json={"doc_type": "invoice"}).json()
    assert json.dumps(doc["data"]["fields"]["total"]["second_opinion"]) == \
        json.dumps({"reader": "Fake reader", "value": "11.10", "agrees": False, "confirms": False})


def test_second_reader_configuration(monkeypatch):
    from documouse import config, crosscheck
    from documouse.crosscheck import SecondReaderError, get_second_reader

    def configure(**env):
        for key in ("SECOND_READER", "PADDLEOCR_VL_URL", "VISION_PROVIDER", "VISION_API_KEY", "VISION_MODEL"):
            monkeypatch.delenv(f"DOCUMOUSE_{key}", raising=False)
        for key, value in env.items():
            monkeypatch.setenv(f"DOCUMOUSE_{key.upper()}", value)
        config.get_settings.cache_clear()
        crosscheck.get_second_reader.cache_clear()

    try:
        configure(second_reader="none")
        assert get_second_reader() is None
        configure(second_reader="paddleocr_vl")
        with pytest.raises(SecondReaderError):
            get_second_reader()
        configure(second_reader="vision", vision_provider="gemini")
        with pytest.raises(SecondReaderError, match="API_KEY"):
            get_second_reader()
        configure(second_reader="vision", vision_provider="gemini", vision_api_key="k")
        assert get_second_reader().name == "gemini-3.8-flash"
        configure(second_reader="vision", vision_provider="ollama")
        with pytest.raises(SecondReaderError, match="VISION_MODEL"):
            get_second_reader()
    finally:
        configure()
