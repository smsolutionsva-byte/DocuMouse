# Evaluation

DocuMouse is measured on two public datasets of real scanned documents. The scripts in
`backend/eval/` run the **same pipeline the app uses** after OCR: PaddleOCR PP-StructureV3 →
classify → extract → validate. Datasets are downloaded separately and nothing from them is
committed to this repository.

| Dataset | What it is | License |
| --- | --- | --- |
| [ICDAR 2019 SROIE](https://github.com/jsdnrs/ICDAR2019-SROIE) ([images on Hugging Face](https://huggingface.co/datasets/jsdnrs/ICDAR2019-SROIE)) | 987 scanned Malaysian till receipts with ground-truth company, date, address and total | CC BY 4.0 |
| [FUNSD](https://guillaumejaume.github.io/FUNSD/) ([guide](https://github.com/crcresearch/FUNSD)) | 199 noisy scanned forms (1980s–90s) with word-level annotations | Non-commercial research use |

## Method

- **No peeking at the test set.** Extraction rules were tuned only on the first 200 SROIE *train*
  receipts. The 361 SROIE *test* receipts were scored once, afterwards.
- **What counts as correct.** Company: exact match after removing spaces and punctuation, so
  `SDN. BHD.` = `SDN BHD`. Date: same calendar day. Total: same amount to the cent.
- **The number that matters most for a review product** is *wrong but marked verified*: a wrong
  value DocuMouse shows with a ✓, so the user might not check it. Wrong values that are flagged
  for review are much less harmful, because the review screen points the user at them.
- Engine: PaddleOCR 3.7, PP-StructureV3, `fast` preset (PP-OCRv5 mobile text models),
  PaddlePaddle 3.2.2, CPU only (4 cores). No LLM.

## Results

### SROIE test set (361 receipts, held out)

| Field | Correct | Missing (“Not detected”) | Wrong | **Wrong but marked verified** | Correct & verified |
| --- | --- | --- | --- | --- | --- |
| Company | 61.2% | 0.0% | 38.8% | **6.1%** | 31.0% |
| Date | 83.9% | 14.4% | 1.7% | **0.8%** | 72.0% |
| Total | 83.1% | 8.0% | 8.9% | **3.9%** | 70.9% |

- Classified as a receipt: 313 / 361 (87%); as an invoice: 43; unknown: 5.
- OCR time: **3.5 s per receipt** on CPU (PaddlePaddle 3.2.2 with oneDNN).

**Before vs after tuning on SROIE train**, both scored on the same test set:

| Field | Before | After |
| --- | --- | --- |
| Company correct | 45.7% | 61.2% |
| Date correct | 47.4% | 83.9% |
| Total correct | 52.9% | 83.1% |
| Receipts classified as receipts | 48% | 87% |
| Total correct *and* marked verified | 17.7% | 70.9% |
| Total wrong but marked verified | 0.6% | 3.9% |

The trade-off is deliberate. The old version flagged every document for review, so almost nothing
was ever "verified" and nothing could be silently wrong. The tuned version verifies most correct
values, at the cost of a few wrong ones getting a ✓.

### Fast vs accurate OCR preset (first 60 SROIE train receipts)

| | `fast` (mobile models, default) | `accurate` (server models) |
| --- | --- | --- |
| Company correct / wrong-but-verified | 61.7% / 6.7% | 65.0% / 1.7% |
| Date correct | 90.0% | 88.3% |
| Total correct | 96.7% | 93.3% |
| Time per receipt | ~3.5 s | ~10.6 s |

`accurate` reads business names better (fewer `SDN BHO`-style character errors) but is 3× slower and
not better on dates or totals. `fast` stays the default. Set `DOCUMOUSE_OCR_PRESET=accurate` if names
matter more than speed.

### FUNSD test set (50 forms)

FUNSD has no invoices or receipts, so it tests the *other document* path:

- **Not forced into a template:** 45 / 50 classified as *other document*. The 5 read as receipts all
  scored 45–51% confidence, below DocuMouse's 60% threshold, so the review screen asks *“DocuMouse
  isn't sure what this document is”* instead of assuming.
- **Reading quality:** PaddleOCR found 81.4% of the annotated words (median 83.6%, worst 37.3%) on these
  old, noisy scans.
- **Robustness:** 50 / 50 processed. One form hit a PaddleX bug in table recognition
  (`'NoneType' object has no attribute 'text_rec_model'`). DocuMouse now retries that page with
  PaddleOCR's `use_ocr_results_with_table_cells=False` option instead of failing.

## What the evaluation changed

Real receipts behaved very differently from clean samples. Fixes that came out of SROIE *train*:

| Problem on real scans | Fix |
| --- | --- |
| Mobile OCR drops spaces: `25/12/20188:13:39PM`, `BOOKTA-K(TAMANDAYA)SDNBHD` | Dates tolerate a glued time or label. Legal suffixes are matched even when glued |
| `22/3-24` (a product code) read as a date | Dates need the same separator twice |
| A garbled `2.90.00` made a whole receipt month-first | Day/month evidence only counts plausible dates |
| `RM`, `AMOUNT（RM）`, `$` on Malaysian receipts | Local currency abbreviations, full-width brackets. ISO codes only next to amounts |
| "Total incl. GST 65.72 → Rounding → TOTAL 65.70" | Labels ranked by how explicit they are. A later cash-rounded total wins |
| "Total Paid 50.00" (cash handed over), "TAX TOTAL 0.40" | Excluded from totals. Totals of a few cents are flagged |
| OCR typos in labels: `Grand Totai`, `TOTALRM21.85` | Label matching tolerates l/i/1 and o/0 confusions. Values are never altered |
| Store address or "TAX" chosen as the business name | Addresses and lone words are rejected. "Not detected" is better than a wrong name |
| Names wrapped over two lines, trailing registration numbers | Wrapped names are joined. `(126926-H)` / `862725-U` are stripped |
| Shops print "TAX INVOICE" on till receipts | Retail signals (cashier, cash/change, time) outweigh it |
| A low-confidence tax value made a correct total look wrong | Unsure optional amounts become one-click suggestions instead of values |

## Known limitations

- **Business names (61%)** are the weakest field. The remaining errors are mostly OCR character slips
  (`SDN BHO`, `Bradvew`), names that exist only in a logo, brand vs legal-entity mismatches
  (`MYDIN MART` vs `TRI SHAAS SDN BHD`), and branch names the annotators included.
- **Missing dates (14%)** are almost all OCR failures on the date itself (`25/04/2017` read as `250412017`).
- **Silent total errors (3.9%)** are mostly OCR misreads of the rounded total label, and delivery
  invoices with returns where several totals are printed.
- SROIE is one country's receipts, and FUNSD has no invoices. Indian GST invoices are covered by the
  samples and fixtures in `backend/tests`, not by a public benchmark yet.
- The optional LLM extraction pass was not part of these runs.

## Reproduce

```bash
cd backend
pip install -e ".[ocr,dev,eval]"

# SROIE: labels from GitHub, images from Hugging Face
git clone https://github.com/jsdnrs/ICDAR2019-SROIE ~/datasets/sroie
python eval/sroie.py fetch --data ~/datasets/sroie
python eval/sroie.py ocr   --data ~/datasets/sroie --split test          # ~20 min on 4 CPU cores
python eval/sroie.py score --data ~/datasets/sroie --split test --show-errors 20

# FUNSD
curl -LO https://guillaumejaume.github.io/FUNSD/dataset.zip && unzip dataset.zip -d ~/datasets/funsd
python eval/funsd.py ocr   --data ~/datasets/funsd/dataset --split testing_data
python eval/funsd.py score --data ~/datasets/funsd/dataset --split testing_data
```

OCR output is cached in `backend/.eval-cache/`, so re-scoring after changing extraction rules takes seconds.
