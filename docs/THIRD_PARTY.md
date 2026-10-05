# Third-party software

DocuMouse itself is MIT licensed. It depends on the following projects, each under its own license.
Check each project's repository for the authoritative terms.

## Document engine

| Project | License | Used for |
| --- | --- | --- |
| [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) 3.x | Apache-2.0 | PP-StructureV3 pipeline: layout, OCR, reading order, tables |
| [PaddleX](https://github.com/PaddlePaddle/PaddleX) 3.x | Apache-2.0 | Pipeline runtime used by PaddleOCR 3.x |
| [PaddlePaddle](https://github.com/PaddlePaddle/Paddle) 3.x | Apache-2.0 | Deep learning runtime |
| PP-StructureV3 models (PP-DocLayout, PP-OCRv5, SLANet/SLANeXt, RT-DETR table cells, PP-LCNet) | Apache-2.0 (see each model card) | Downloaded on first run, not redistributed by DocuMouse |

## Backend (Python)

| Package | License |
| --- | --- |
| FastAPI | MIT |
| Uvicorn | BSD-3-Clause |
| SQLAlchemy | MIT |
| psycopg 3 | LGPL-3.0 (used as an unmodified library) |
| Pydantic, pydantic-settings | MIT |
| python-multipart | Apache-2.0 |
| HTTPX | BSD-3-Clause |
| Pillow | MIT-CMU (HPND) |
| pypdfium2 (+ PDFium) | Apache-2.0 / BSD-3-Clause |
| pytest, ReportLab (dev only) | MIT, BSD |

## Frontend (JavaScript)

| Package | License |
| --- | --- |
| Next.js, React | MIT |
| Tailwind CSS | MIT |
| Motion | MIT |
| Lucide icons | ISC |
| Instrument Sans, Instrument Serif, Inter (via Fontsource) | SIL Open Font License 1.1 |
