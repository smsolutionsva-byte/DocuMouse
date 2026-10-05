"""Extraction orchestrator: rules first, LLM second, then reconcile."""

from __future__ import annotations

from ..document_data import DocumentData, FieldValue, Source, Suggestion
from ..llm.base import LLMProvider
from ..processing.types import RawDocument
from . import layout
from .llm_extract import LLMField, llm_extract
from .rules import RuleExtractor
from .schema import schema_for
from .tables import build_tables, items_from_text_rows


def extract(raw: RawDocument, doc_type: str, *, llm: LLMProvider | None = None) -> DocumentData:
    rules = RuleExtractor(raw)
    fields = rules.extract(doc_type)
    if llm is not None and schema_for(doc_type):
        llm_fields = llm_extract(raw, doc_type, llm, dayfirst=rules.dayfirst)
        fields = {key: reconcile(value, llm_fields.get(key)) for key, value in fields.items()}

    tables = build_tables(raw, want_line_items=doc_type in ("invoice", "receipt"))
    if doc_type == "receipt" and not any(t.role == "line_items" for t in tables):
        items = items_from_text_rows(raw)
        if items is not None:
            tables.insert(0, items)
    for i, table in enumerate(tables, start=1):
        table.id = f"t{i}"
    data = DocumentData(doc_type=doc_type, fields=fields, tables=tables)
    data.next_table_id = len(tables) + 1
    return data


def reconcile(rule: FieldValue, model: LLMField | None) -> FieldValue:
    """Combine the rule-based value with the (fact-checked) LLM value."""
    if model is None:
        return rule
    if not model.grounded:
        # Not printed in the document: never used as the value, only offered.
        if rule.value is None and model.proposed:
            rule = rule.model_copy(deep=True)
            rule.suggestion = Suggestion(
                value=model.proposed,
                reason="The AI suggested this, but DocuMouse couldn't find it in the document.",
            )
        return rule
    source = _source(model)
    if rule.value is None:
        conf = 0.8 * min((ln.confidence for ln in model.lines), default=0.8)
        return FieldValue(value=model.value, raw=model.lines[0].text if model.lines else model.value,
                          confidence=round(conf, 3), source=source, origin="llm")
    if _same(rule.value, model.value):
        merged = rule.model_copy(deep=True)
        merged.origin = "ocr+llm"
        # Two independent readings agree: that's worth a lot.
        merged.confidence = round(max(rule.confidence, min(0.97, rule.confidence + 0.25)), 3)
        merged.notes = [n for n in merged.notes if "please check" not in n.lower() and "no “date” label" not in n.lower()]
        return merged
    # They disagree: keep the LLM's grounded reading but make the user decide.
    return FieldValue(
        value=model.value,
        raw=model.lines[0].text if model.lines else model.value,
        confidence=0.5,
        source=source,
        origin="llm",
        suggestion=Suggestion(value=rule.value or "", reason="DocuMouse also found this value."),
        notes=["Two readings of the document disagree — please pick the right one."],
    )


def _same(a: str | None, b: str | None) -> bool:
    if a is None or b is None:
        return False
    return " ".join(a.lower().split()) == " ".join(b.lower().split())


def _source(model: LLMField) -> Source | None:
    if not model.lines:
        return None
    page = model.lines[0].page
    return Source(page=page, bbox=layout.union_bbox([ln for ln in model.lines if ln.page == page]))
