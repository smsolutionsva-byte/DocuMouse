.PHONY: db backend-install backend frontend-install frontend test lint

VENV ?= backend/.venv
PY := $(VENV)/bin/python

db:            ## Start PostgreSQL in Docker
	docker compose up -d postgres

backend-install:  ## Create a virtualenv and install the backend with PaddleOCR
	python3 -m venv $(VENV)
	$(PY) -m pip install --upgrade pip
	cd backend && ../$(PY) -m pip install -e ".[ocr,dev]"

backend:       ## Run the API on :8000 (auto-reload)
	cd backend && ../$(PY) -m uvicorn documouse.main:app --reload --port 8000

frontend-install:
	cd frontend && npm install

frontend:      ## Run the web app on :3000
	cd frontend && npm run dev

test:          ## Backend tests (no OCR models needed)
	cd backend && ../$(PY) -m pytest -q

lint:
	cd frontend && npm run lint && npm run typecheck
