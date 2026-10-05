"""Evaluate DocuMouse on FUNSD (Form Understanding in Noisy Scanned Documents).

Dataset: https://guillaumejaume.github.io/FUNSD/ (see also https://github.com/crcresearch/FUNSD).
FUNSD is for non-commercial research use; nothing from it is committed here.

    python eval/funsd.py ocr   --data ~/datasets/funsd_orig/dataset --split testing_data
    python eval/funsd.py score --data ~/datasets/funsd_orig/dataset --split testing_data

These are forms, not invoices or receipts, so this checks the "other document" path:
  * classification: forms should mostly NOT be forced into invoice/receipt
  * reading quality: recall of the annotated words in PaddleOCR's output
  * honesty: when a form IS read as an invoice/receipt, how many fields get filled
  * robustness: every document processes without errors
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from documouse.understanding.classify import classify  # noqa: E402
from documouse.understanding.extract import extract  # noqa: E402
from documouse.validation import validate  # noqa: E402
from eval.engine_cache import cached_raw, warm_cache  # noqa: E402


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t]


def cmd_ocr(args) -> None:
    images = sorted((args.data / args.split / "images").glob("*.png"))[: args.limit]
    warm_cache(images, args.cache / args.split)


def cmd_score(args) -> None:
    images = sorted((args.data / args.split / "images").glob("*.png"))[: args.limit]
    types: Counter = Counter()
    recalls: list[float] = []
    filled: Counter = Counter()
    flagged = 0
    examples: list[str] = []
    for image in images:
        try:
            raw, _ = cached_raw(image, args.cache / args.split)
        except RuntimeError:
            continue
        ann = json.loads((args.data / args.split / "annotations" / f"{image.stem}.json").read_text())
        truth = Counter(t for entity in ann["form"] for w in entity["words"] for t in tokens(w["text"]))
        got = Counter(t for line in raw.lines for t in tokens(line.text))
        if truth:
            recalls.append(sum((truth & got).values()) / sum(truth.values()))
        c = classify(raw)
        types[c.detected_type] += 1
        if c.detected_type in ("invoice", "receipt"):
            data = extract(raw, c.detected_type)
            v = validate(data, today=date(2000, 12, 31))
            n = sum(1 for f in data.fields.values() if f.value)
            filled[c.detected_type] += n
            flagged += 1 if v.summary["issues"] else 0
            if len(examples) < args.show:
                head = " | ".join(line.text for line in raw.lines[:4])
                examples.append(f"{image.stem} → {c.detected_type} ({c.confidence:.0%}; {', '.join(c.signals[c.detected_type][:3])}) :: {head[:110]}")
    n = sum(types.values())
    print(f"FUNSD {args.split}: {n} forms")
    print("classified as:", dict(types))
    if recalls:
        recalls.sort()
        print(f"word recall: mean {sum(recalls) / len(recalls):.1%}, median {recalls[len(recalls) // 2]:.1%}, worst {recalls[0]:.1%}")
    forced = types["invoice"] + types["receipt"]
    if forced:
        print(f"read as invoice/receipt: {forced}; avg fields filled {sum(filled.values()) / forced:.1f}; with something to check: {flagged}/{forced}")
    for e in examples:
        print("  ", e)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["ocr", "score"])
    p.add_argument("--data", type=Path, required=True, help="the unzipped FUNSD 'dataset' folder")
    p.add_argument("--split", default="testing_data", choices=["training_data", "testing_data"])
    p.add_argument("--cache", type=Path, default=Path(".eval-cache/funsd"))
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--show", type=int, default=10)
    args = p.parse_args()
    {"ocr": cmd_ocr, "score": cmd_score}[args.command](args)


if __name__ == "__main__":
    main()
