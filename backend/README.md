# DocuMouse backend

The FastAPI backend reads documents with PaddleOCR, extracts fields and tables,
stores review history, and exports CSV files.

Install the API and document engine from this directory:

```bash
pip install -e '.[ocr]'
```

See the [project README](../README.md) for configuration and development, the
[hosting guide](../docs/hosting.md) for a server deployment, and the
[PC test-site guide](../docs/pc-test-site.md) for a temporary local-hosted preview.
