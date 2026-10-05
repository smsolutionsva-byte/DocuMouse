# 🐁 DocuMouse

**Drop your documents in. DocuMouse figures them out, cleans the data, lets you review it, and gives you a spreadsheet.**

DocuMouse is an open-source document processing app for freelancers, small businesses and anyone who
copies numbers from PDFs into spreadsheets by hand. You never pick a template or learn what OCR is:
drop invoices and receipts in, check what DocuMouse found next to the original, fix anything in plain
language, and export a CSV.

Under the hood, [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR)'s **PP-StructureV3** pipeline does
all the low-level reading (layout, text, reading order, tables). DocuMouse adds classification, field
extraction, deterministic validation, a review screen, versioned editing and export on top.

> **Status: early MVP.** The first vertical slice works end to end with the real PaddleOCR engine:
> upload → PP-StructureV3 → classification → invoice/receipt extraction → validation → review → edit → approve → CSV.
> See [What works today](#what-works-today), [Try it](#try-it-with-the-sample-documents) and [Roadmap](#roadmap).

---

## How well it works

Measured on 361 held-out real scanned receipts ([ICDAR 2019 SROIE](https://github.com/jsdnrs/ICDAR2019-SROIE)),
CPU only, no LLM:

| Field | Correct | Wrong but marked ✓ verified |
| --- | --- | --- |
| Total | 83.1% | 3.9% |
| Date | 83.9% | 0.8% |
| Business name | 61.2% | 6.1% |

On 50 noisy scanned forms ([FUNSD](https://guillaumejaume.github.io/FUNSD/)), 90% are recognised as
"other documents" rather than forced into an invoice template, and the rest prompt the user to choose.
Full method, before/after numbers and known limitations: [docs/evaluation.md](docs/evaluation.md).

## What works today

| Area | Status |
| --- | --- |
| Upload | Drag-and-drop anywhere on the page, multiple files, PDF / JPG / PNG / WebP / TIFF, per-file progress through *Uploading → Reading → Understanding → Extracting → Checking → Ready for review* |
| Reading | PaddleOCR 3.x **PP-StructureV3**: orientation, layout, text detection/recognition, reading order, table recognition |
| Classification | Invoice / receipt / other, with confidence and reasons. Asks you when unsure; warns if your pick looks wrong ("This looks more like a receipt than an invoice") |
| Extraction | Invoices: vendor, number, dates, currency, subtotal, discount, tax, CGST/SGST/IGST, total, GSTIN, billed-to, line items. Receipts: merchant, date, time, payment method, currency, amounts, GST, line items (also when the receipt has no ruled table). Missing values stay **Not detected**, never invented. Day/month order is settled from the page (e.g. a `25/09` elsewhere) or the currency's convention, otherwise you're asked |
| Validation | Deterministic: amount/date/currency formats, GSTIN checksum, *subtotal − discount + taxes = total*, CGST = SGST, `qty × price = amount` per row, rows add up to the subtotal. Nothing is auto-"fixed" |
| Review | Original document beside the extracted data. Selecting a field or row highlights where it came from. Uncertain fields are marked with the reason |
| Tables | Spreadsheet-like editing: edit cells, add/delete/merge rows, rename/move/insert/delete columns, split and merge columns (with a live preview), split tables, mark total rows |
| AI edits | Plain-language requests ("you merged quantity and price, separate them") become structured operations, previewed as before → after, applied only when you click **Approve** |
| History | Every change is a new version. Undo/redo (⌘Z / ⌘⇧Z), version history, restore any version. The original upload is never modified |
| Export | A short final review, then CSV ("everything", or "one row per line item"). Library export: one row per document |
| Library | Search across extracted values, filter by type, status and date. Duplicate detection by file hash, invoice number + vendor, or vendor + date + total (flags only, never deletes) |

## Architecture

A modular monolith: one FastAPI service, one Next.js app, PostgreSQL, and files on local disk.

```mermaid
flowchart TD
    UI["Next.js app<br/>upload · review · library"] -->|/api proxy| API[FastAPI]
    API --> Store[(Storage<br/>originals · page images)]
    API --> DB[(PostgreSQL<br/>documents · versions)]
    API --> Q[Background worker]
    Q --> Pages[PDF/image → page images]
    Pages --> Engine["Document engine<br/>PaddleOCR PP-StructureV3"]
    Engine --> Raw["RawDocument<br/>text lines + boxes · layout · tables"]
    Raw --> Classify[Classification]
    Classify --> Extract["Extraction<br/>rules ± LLM (fact-checked)"]
    Extract --> Validate[Deterministic validation]
    Validate --> V1[Version 1]
    API --> Edit["Edit engine<br/>validated operations"]
    Assistant["AI assistant<br/>request → operations"] --> Edit
    Edit --> Versions[New version · undo/redo]
    Versions --> Export[CSV export]
```

Read [docs/architecture.md](docs/architecture.md) for the design decisions: why an LLM is never
trusted, how versioning works, and where to plug in a new engine, storage backend or LLM provider.

```
backend/documouse/
  processing/      pages → document engine (engines/paddle.py) → RawDocument; pipeline + worker
  understanding/   classify.py, rules.py (extraction), tables.py, llm_extract.py, schema.py
  validation/      deterministic checks
  editing/         operations.py (the only way data changes), assistant.py, preview.py
  versioning.py    immutable versions, undo/redo/restore
  export/          CSV
  llm/             provider abstraction (any OpenAI-compatible endpoint)
  storage/         local disk (S3-compatible can be added behind the same interface)
frontend/src/
  components/review/   the review screen
  components/upload/   drop zone + processing queue
  app/globals.css      design tokens
```

## Running it locally

### Requirements

- **Python 3.10–3.13** (PaddlePaddle 3.x publishes wheels for these)
- **Node.js 20+**
- **PostgreSQL 14+** (or Docker: `docker compose up -d`)
- About **8 GB RAM** for PP-StructureV3 on CPU. A GPU is optional.
- Internet access on first run so PaddleOCR can download its models (see below)

### 1. Database

```bash
docker compose up -d          # or use your own PostgreSQL and set DOCUMOUSE_DATABASE_URL
```

### 2. Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[ocr,dev]"   # FastAPI app + PaddlePaddle + PaddleOCR (PP-StructureV3)
cp .env.example .env          # adjust if needed
uvicorn documouse.main:app --reload --port 8000
```

Tables are created on startup. Run the tests with `pytest` (they don't need OCR models).

### 3. Frontend

```bash
cd frontend
npm install
cp .env.example .env.local    # DOCUMOUSE_API_URL=http://localhost:8000
npm run dev                   # http://localhost:3000
```

Or use the `Makefile`: `make db`, `make backend-install`, `make backend`, `make frontend-install`, `make frontend`.

### PaddleOCR / PP-StructureV3 notes

- DocuMouse uses PaddleOCR **3.7** (`paddleocr[doc-parser]`) with **PaddlePaddle 3.2.2** (pinned). PaddlePaddle 3.3.x
  breaks CPU inference with oneDNN, the Linux default
  (`ConvertPirAttribute2RuntimeAttribute not support`, see
  [PaddleOCR#17539](https://github.com/PaddlePaddle/PaddleOCR/issues/17539)). With oneDNN switched off
  (`DOCUMOUSE_OCR_ENABLE_MKLDNN=false`) 3.3.x works but was about 4× slower in our tests.
- The CPU wheel comes from PyPI. For NVIDIA GPUs, install `paddlepaddle-gpu` following the
  [PaddlePaddle install guide](https://www.paddlepaddle.org.cn/en/install/quick), then set `DOCUMOUSE_OCR_DEVICE=gpu:0`.
- **Models download on first use** (layout, text detection/recognition, table models) into `~/.paddlex/official_models`.
  The default source is Hugging Face (`huggingface.co`). Set `PADDLE_PDX_MODEL_SOURCE` to `modelscope`, `aistudio` or `bos`
  if that host is unreachable. If no model host is reachable, documents fail with
  *"DocuMouse's reading engine isn't available right now"* and the technical reason is shown to whoever runs DocuMouse.
- `DOCUMOUSE_OCR_PRESET=fast` (default) swaps in the PP-OCRv5 **mobile** text models, which are much quicker on CPU.
  `accurate` uses PP-StructureV3's server models. Formula, chart and seal recognition are turned off: invoices don't need them.
- Measured on a 4-core CPU (fast preset, PaddlePaddle 3.2.2): ~8 s for a scanned A4 invoice, ~2 s for a till receipt,
  plus ~10 s once to load the models. The first run also downloads them (~0.9 GB). Processing runs in the background,
  and leaving the page doesn't stop it.
- PP-StructureV3's per-table orientation check is turned off: pages are already straightened, and on small
  borderless tables (a totals block) it returned the table rotated 180°.

### Try it with the sample documents

`backend/tests/samples/` has a synthetic GST invoice (PDF), a skewed "scanned" copy of it (JPG) and a café receipt
(PNG). Regenerate them with `python tests/samples/make_samples.py`. Drop them on the home page: all three should come
back with every field verified, all math checks passing, and the scan flagged as a duplicate of the PDF.

`backend/tests/fixtures_real/` holds what PaddleOCR actually returned for these files. `test_real_engine_output.py`
runs the extractor against it, so `pytest` checks behaviour on real engine output without needing the models.
Re-record with `python tests/record_engine_output.py` after upgrading PaddleOCR.

### Optional: an LLM

Without an LLM, DocuMouse uses its deterministic extractor, and the assistant understands simple commands
("delete row 3", "change the vendor to Acme", "split Qty Price into Qty and Price").
Connect any OpenAI-compatible endpoint to get natural-language editing and a second, fact-checked extraction pass:

```bash
# backend/.env
DOCUMOUSE_LLM_PROVIDER=groq          # or openrouter, ollama, lmstudio, openai_compatible
DOCUMOUSE_LLM_MODEL=<model id>
DOCUMOUSE_LLM_API_KEY=<key>          # stays on the server
```

Every value the LLM proposes must be found in PaddleOCR's text, or it's discarded (shown only as a suggestion).
Every edit it proposes is a validated operation that you preview and approve.

## Environment variables

All backend settings use the `DOCUMOUSE_` prefix. See [`backend/.env.example`](backend/.env.example) for the full list.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DOCUMOUSE_DATABASE_URL` | `postgresql+psycopg://documouse:documouse@localhost:5432/documouse` | SQLAlchemy URL |
| `DOCUMOUSE_STORAGE_DIR` | `./data` | Originals, page images, engine output |
| `DOCUMOUSE_MAX_UPLOAD_MB` / `DOCUMOUSE_MAX_PAGES` | `25` / `20` | Upload limits |
| `DOCUMOUSE_PDF_RENDER_DPI` | `200` | PDF page rendering resolution |
| `DOCUMOUSE_OCR_PRESET` | `fast` | `fast` (mobile text models) or `accurate` |
| `DOCUMOUSE_OCR_LANG` | `en` | Recognition language for the `accurate` preset |
| `DOCUMOUSE_OCR_DEVICE` | auto | `cpu`, `gpu:0`, … |
| `DOCUMOUSE_OCR_ENABLE_MKLDNN` | PaddleOCR default | Set `false` if you must run PaddlePaddle 3.3.x on CPU |
| `DOCUMOUSE_PROCESSING_WORKERS` | `1` | Documents processed in parallel |
| `DOCUMOUSE_LLM_PROVIDER` | `none` | `groq`, `openrouter`, `ollama`, `lmstudio`, `openai_compatible` |
| `DOCUMOUSE_LLM_MODEL` / `_API_KEY` / `_BASE_URL` | – | LLM connection |
| `PADDLE_PDX_MODEL_SOURCE` | `huggingface` | PaddleOCR model download host |
| `PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK` | – | `True` skips the host check at startup once models are downloaded |
| `DOCUMOUSE_API_URL` (frontend) | `http://localhost:8000` | Where Next.js proxies `/api` |

## Roadmap

Built deliberately small. Next up, roughly in order:

- [x] Run the real PaddleOCR pipeline end to end (PDF, scan, receipt) and tune the extractor on its output
- [x] Receipt line items when PP-StructureV3 doesn't detect a table
- [x] Benchmark on real scanned receipts and forms (SROIE, FUNSD), see [docs/evaluation.md](docs/evaluation.md)
- [ ] Improve business-name extraction (61% on SROIE): logo-only names, brand vs legal entity
- [ ] A public benchmark for invoices (including Indian GST invoices), plus phone photos
- [ ] Authentication and per-user workspaces (currently **single-user, no login**: run it locally or behind your own auth)
- [ ] Alembic migrations (tables are created on startup today)
- [ ] XLSX / JSON export
- [ ] Click text on the original to fill a field
- [ ] More document types: purchase orders, bank statements
- [ ] Later: due-date tracking, paid/unpaid, email ingestion (`you@inbox.documouse.app`)

## Contributing

Issues and pull requests are welcome. Before opening a PR:

```bash
cd backend && pytest
cd frontend && npm run lint && npm run typecheck
```

Keep the product simple: if a feature needs a settings page to explain it, it probably needs more design first.

## Licenses

DocuMouse is [MIT licensed](LICENSE). It builds on PaddleOCR, PaddlePaddle and PaddleX (Apache-2.0) and their
models (Apache-2.0), plus other open-source packages. See [docs/THIRD_PARTY.md](docs/THIRD_PARTY.md).
