"""Evaluate DocuMouse on ICDAR 2019 SROIE (scanned receipts).

Dataset: https://github.com/jsdnrs/ICDAR2019-SROIE (labels) and
https://huggingface.co/datasets/jsdnrs/ICDAR2019-SROIE (images), CC BY 4.0.
Nothing from the dataset is committed to this repository.

    python eval/sroie.py fetch  --data ~/datasets/sroie          # images from Hugging Face
    python eval/sroie.py ocr    --data ~/datasets/sroie --split train
    python eval/sroie.py score  --data ~/datasets/sroie --split train [--show-errors 20]

Scoring runs the exact app pipeline after OCR: classify → extract → validate.
For each key field it reports accuracy, how often the field is missing, and how
often a WRONG value was shown as verified (a silent error, the number that
matters most for a review-based product).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from documouse.understanding.classify import classify  # noqa: E402
from documouse.understanding.extract import extract  # noqa: E402
from documouse.understanding.parsing import find_dates, parse_amount  # noqa: E402
from documouse.validation import validate  # noqa: E402
from eval.engine_cache import cached_raw, warm_cache  # noqa: E402

FIELD_MAP = {  # SROIE key -> DocuMouse field per document type
    "company": {"receipt": "merchant", "invoice": "vendor"},
    "date": {"receipt": "date", "invoice": "invoice_date"},
    "total": {"receipt": "total", "invoice": "total"},
}


def norm_text(s: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def same(key: str, truth: str, got: str | None) -> bool:
    if got is None:
        return False
    if key == "total":
        a, b = parse_amount(truth), parse_amount(got)
        return a is not None and b is not None and abs(a - b) < Decimal("0.005")
    if key == "date":
        dates = find_dates(truth, dayfirst=True, allow_compact=True)
        return bool(dates) and dates[0].value.isoformat() == got
    return norm_text(truth) == norm_text(got)


def load_labels(data: Path, split: str) -> list[dict]:
    rows = [json.loads(line) for line in (data / "data" / split / "metadata.jsonl").read_text().splitlines() if line.strip()]
    return rows


def cmd_fetch(args) -> None:
    import pyarrow.parquet as pq
    from huggingface_hub import hf_hub_download

    for split in ("train", "test"):
        path = hf_hub_download("jsdnrs/ICDAR2019-SROIE", f"data/{split}-00000-of-00001.parquet", repo_type="dataset")
        out = args.data / "images" / split
        out.mkdir(parents=True, exist_ok=True)
        table = pq.read_table(path, columns=["key", "image"])
        for row in table.to_pylist():
            (out / f"{row['key']}.jpg").write_bytes(row["image"]["bytes"])
        print(split, table.num_rows, "images")


def cmd_ocr(args) -> None:
    labels = load_labels(args.data, args.split)[: args.limit]
    images = [args.data / "images" / args.split / f"{r['key']}.jpg" for r in labels]
    warm_cache(images, args.cache / args.split)


def cmd_score(args) -> None:
    labels = load_labels(args.data, args.split)[: args.limit]
    stats: dict[str, Counter] = defaultdict(Counter)
    types: Counter = Counter()
    errors: list[str] = []
    review_counts: list[int] = []
    checks: Counter = Counter()
    seconds = time.time()
    used = 0
    for row in labels:
        try:
            raw, _ = cached_raw(args.data / "images" / args.split / f"{row['key']}.jpg", args.cache / args.split)
        except RuntimeError:
            continue
        used += 1
        c = classify(raw)
        types[c.detected_type] += 1
        doc_type = c.detected_type if c.detected_type in ("receipt", "invoice") else "receipt"
        data = extract(raw, doc_type)
        v = validate(data, today=date(2019, 12, 31))
        review_counts.append(v.summary["issues"])
        for ch in v.checks:
            checks[f"{ch.id}:{ch.status}"] += 1
        for key, mapping in FIELD_MAP.items():
            truth = row["entities"].get(key)
            if not truth:
                continue
            fkey = mapping[doc_type]
            got = data.fields[fkey].value if fkey in data.fields else None
            status = v.fields.get(fkey, {}).get("status")
            s = stats[key]
            s["total"] += 1
            if got is None:
                s["missing"] += 1
            elif same(key, truth, got):
                s["correct"] += 1
                s["correct_verified" if status == "verified" else "correct_flagged"] += 1
            else:
                s["wrong"] += 1
                s["wrong_silent" if status == "verified" else "wrong_flagged"] += 1
                if key == "company" and SequenceMatcher(None, norm_text(truth), norm_text(got)).ratio() > 0.9:
                    s["near_miss"] += 1
            if (got is None or not same(key, truth, got)) and len(errors) < args.show_errors * 3:
                errors.append(f"{row['key']} {key:7} truth={truth!r:45} got={got!r} [{status}]")

    print(f"SROIE {args.split}: {used} receipts scored in {time.time() - seconds:.1f}s")
    print(f"classified as: {dict(types)}")
    print(f"{'field':8} {'correct':>8} {'missing':>8} {'wrong':>6} {'wrong but verified':>19} {'correct & verified':>19}")
    for key in FIELD_MAP:
        s = stats[key]
        n = s["total"] or 1
        print(f"{key:8} {s['correct'] / n:8.1%} {s['missing'] / n:8.1%} {s['wrong'] / n:6.1%} "
              f"{s['wrong_silent'] / n:19.1%} {s['correct_verified'] / n:19.1%}")
    flagged = sum(1 for r in review_counts if r)
    print(f"documents with something to check: {flagged}/{len(review_counts)}")
    print("checks:", dict(sorted(checks.items())))
    if args.show_errors:
        by_key = defaultdict(list)
        for e in errors:
            by_key[e.split()[1]].append(e)
        for key, rows in by_key.items():
            print(f"--- {key} errors")
            for e in rows[: args.show_errors]:
                print("  ", e)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["fetch", "ocr", "score"])
    p.add_argument("--data", type=Path, required=True, help="SROIE checkout (labels in data/, images in images/)")
    p.add_argument("--split", default="train", choices=["train", "test"])
    p.add_argument("--cache", type=Path, default=Path(".eval-cache/sroie"))
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--show-errors", type=int, default=0)
    args = p.parse_args()
    {"fetch": cmd_fetch, "ocr": cmd_ocr, "score": cmd_score}[args.command](args)


if __name__ == "__main__":
    main()
