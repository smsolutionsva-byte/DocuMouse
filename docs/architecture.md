# Architecture

DocuMouse is a **modular monolith**: one FastAPI process (API + in-process background worker),
one Next.js app, PostgreSQL, and a storage directory. Each layer below is a separate Python package with a
narrow interface, so any of them can be swapped or split out later without touching the others.

## The pipeline

```
original file ──► page images ──► document engine ──► RawDocument ──► classify ──► extract ──► validate ──► version 1
 (never changed)   (pypdfium2/      (PaddleOCR          (engine-        (rules)       (rules ±     (deterministic)
                    Pillow)          PP-StructureV3)     neutral)                      LLM)
```

1. **Pages** (`processing/pages.py`). PDFs are rendered at `DOCUMOUSE_PDF_RENDER_DPI`, and images are EXIF-rotated.
   The **same images** go to the engine and to the review viewer, so every coordinate lines up exactly.
2. **Document engine** (`processing/engines/`). `PaddleStructureEngine` runs PaddleOCR's `PPStructureV3` and
   converts its output (`overall_ocr_res`, `parsing_res_list`, HTML tables) into a `RawDocument`: text lines with
   normalised boxes and confidences, layout blocks, and tables as grids. If PP-StructureV3 straightens a rotated page,
   the corrected image replaces the page image. DocuMouse doesn't do any OCR or table recognition itself.
3. **Classification** (`understanding/classify.py`). Weighted, explainable signals ("Says Tax Invoice",
   "Shows card or UPI payment", narrow till-roll shape) turn into a probability per type. Below 60% the
   review screen asks the user. If the user chose a type at upload and DocuMouse is ≥70% sure it's something else,
   it asks before going along with it.
4. **Extraction** (`understanding/`).
   - `rules.py` finds labelled values using text *and* geometry: same line, right neighbour, or the line below.
     It then parses amounts, dates (flagging day/month ambiguity), GSTINs and currencies. Every value keeps a
     pointer to the exact box it came from.
   - `tables.py` picks the line-item table from PP-StructureV3's tables by header semantics, assigns column roles,
     merges tables continued across pages and marks total rows.
   - `llm_extract.py` (optional) asks an LLM to map the OCR lines to fields **with citations**. Each value is then
     checked against the cited text deterministically. Ungrounded values are never used; they show only as
     suggestions. When the rules and the LLM disagree, the user decides.
5. **Validation** (`validation/checks.py`). Pure functions over the data: formats, GSTIN checksum, totals arithmetic
   (with discount-before/after-tax and rounding variants), CGST = SGST, per-row `qty × price`, rows → subtotal.
   Validation never edits values. Values confirmed by a passing arithmetic check count as verified.

## Data model

- `documents`: the upload (hash, storage key, status), classification, page metadata, and a few columns
  denormalised from the current version for search and filters.
- `document_versions`: immutable snapshots of `DocumentData` (fields + tables) as JSON, with author
  (`system`/`user`/`ai`), message and the operations that produced them.

### Versioning, undo and redo

Versions form a tree. `documents.head_version_id` points at the current one.

- An edit creates a child of the head. The client sends `base_version_id`, and a stale base returns `409`, so two tabs can't silently overwrite each other.
- **Undo** moves the head to its parent. **Redo** moves it to the most recently created child.
- **Restore** copies an old version into a new one, so restoring can itself be undone.
- Nothing is deleted, and the original upload is stored separately and never modified.

## Editing: the only way data changes

`editing/operations.py` defines a closed set of operations (`set_field`, `set_cell`, `split_column`,
`merge_columns`, `split_table`, `delete_rows`, …). Typing in a field, using a table menu and approving an AI
suggestion all go through the same path:

```
request ─► parse (pydantic, discriminated union) ─► apply to a copy (validates ids/arguments) ─► preview ─► approve ─► new version
```

The **assistant** (`editing/assistant.py`) only *proposes* operations. With an LLM it sends the document state
and the operation catalogue and gets back JSON operations. They're parsed, dry-run and previewed server-side.
Without an LLM, a small pattern matcher handles common requests. The LLM never touches the database and can't
express SQL or code.

## Extension points

| To add | Implement | Register in |
| --- | --- | --- |
| A document engine | `DocumentEngine.process(pages) -> EngineResult` | `processing/engines/__init__.py` |
| A storage backend (S3, GCS…) | `Storage` protocol (`put/get/exists/delete_prefix`) | `storage/__init__.py` |
| An LLM provider | `LLMProvider.complete_json` (most need no code: they're OpenAI-compatible) | `llm/__init__.py` |
| A document type | a `FieldDef` schema + label hints | `understanding/schema.py` |
| An export format | a function from `DocumentData` | `export/` + a route |

## Background work

`processing/runner.py` is a thread pool fed from the API. Document status lives in the database, so on restart
anything unfinished is re-queued. When processing needs to scale out, this module is the one to replace with a
real queue (RQ/Celery/Arq) and a separate worker process. Nothing else changes.

## Frontend

Next.js App Router. The browser only talks to the Next.js origin, which proxies `/api/*` to FastAPI
(`next.config.ts`), so no backend URL or API key reaches the client. The design system lives in
`src/app/globals.css` (tokens) and `src/components/ui/`. The review screen (`src/components/review/`) is the core of
the product: everything else reuses its language.
