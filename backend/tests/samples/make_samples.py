"""Generate sample documents for trying DocuMouse end to end.

    python tests/samples/make_samples.py

Writes a GST tax invoice (PDF), a scanned-looking copy of it (JPG, slightly
rotated with noise) and a till receipt (PNG). These are synthetic documents for
testing the real PaddleOCR pipeline; no real company data.
"""

from __future__ import annotations

import io
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle

OUT = Path(__file__).parent
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def invoice_pdf(path: Path) -> None:
    pdfmetrics.registerFont(TTFont("DV", FONT))
    pdfmetrics.registerFont(TTFont("DVB", FONT_BOLD))
    s = lambda size=9.5, bold=False, align=0: ParagraphStyle("x", fontName="DVB" if bold else "DV", fontSize=size, leading=size * 1.35, alignment=align)  # noqa: E731

    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm)
    head = Table(
        [[Paragraph("Nimbus Cloud Services Pvt Ltd", s(15, True)), Paragraph("TAX INVOICE", s(15, True, 2))],
         [Paragraph("4th Floor, Prestige Tower, MG Road<br/>Bengaluru, Karnataka 560001<br/>GSTIN: 29AABCN1234M1ZD", s()),
          Paragraph("Invoice No: NCS/2026/0417<br/>Invoice Date: 12/09/2026<br/>Due Date: 12/10/2026", s(9.5, False, 2))]],
        colWidths=[105 * mm, 69 * mm],
    )
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    bill = Paragraph("<b>Bill To:</b><br/>Mouse &amp; Cheese Traders<br/>22 Lake Road, Kolkata 700029<br/>GSTIN: 19AAFCM5678Q1ZF", s())

    rows = [
        ["#", "Description", "HSN/SAC", "Qty", "Rate", "Amount"],
        ["1", "Cloud hosting - Standard plan (Sep)", "998315", "1", "12,000.00", "12,000.00"],
        ["2", "Managed database add-on", "998315", "2", "2,500.00", "5,000.00"],
        ["3", "SSL certificate (1 year)", "998319", "1", "1,500.00", "1,500.00"],
        ["4", "Support hours", "998313", "3", "1,200.00", "3,600.00"],
    ]
    items = Table(rows, colWidths=[9 * mm, 72 * mm, 22 * mm, 13 * mm, 27 * mm, 31 * mm])
    items.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "DV", 9.5),
        ("FONT", (0, 0), (-1, 0), "DVB", 9.5),
        ("GRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#888888")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#efefef")),
        ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    totals = Table(
        [["Sub Total", "22,100.00"], ["CGST @ 9%", "1,989.00"], ["SGST @ 9%", "1,989.00"],
         [Paragraph("<b>Grand Total</b>", s(11)), Paragraph("<b>₹26,078.00</b>", s(11, False, 2))]],
        colWidths=[40 * mm, 35 * mm], hAlign="RIGHT",
    )
    totals.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "DV", 9.5), ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                                ("LINEABOVE", (0, 3), (-1, 3), 0.8, colors.black)]))
    doc.build([head, Spacer(1, 9 * mm), bill, Spacer(1, 8 * mm), items, Spacer(1, 6 * mm), totals, Spacer(1, 14 * mm),
               Paragraph("Bank: HDFC Bank · A/C 50200012345678 · IFSC HDFC0000123", s(8.5)),
               Paragraph("Thank you for your business.", s(8.5))])


def scanned_copy(pdf: Path, path: Path) -> None:
    import pypdfium2 as pdfium

    page = pdfium.PdfDocument(str(pdf))[0]
    img = page.render(scale=150 / 72).to_pil().convert("L")
    random.seed(7)
    img = img.rotate(-1.4, resample=Image.BICUBIC, expand=True, fillcolor=255)
    # Paper grain + a slightly grey, uneven background, like a cheap office scanner.
    noise = Image.effect_noise(img.size, 40)
    img = Image.blend(img, noise, 0.07).point(lambda v: int(v * 0.94 + 4))
    img = img.filter(ImageFilter.GaussianBlur(0.5))
    img.convert("RGB").save(path, quality=72)


def receipt_png(path: Path) -> None:
    w, h = 576, 1500
    img = Image.new("RGB", (w, h), (252, 252, 250))
    d = ImageDraw.Draw(img)
    f = lambda size, bold=False: ImageFont.truetype(FONT_BOLD if bold else FONT, size)  # noqa: E731
    y = 40

    def line(left: str, right: str = "", size: int = 22, bold: bool = False, center: bool = False):
        nonlocal y
        font = f(size, bold)
        if center:
            d.text(((w - d.textlength(left, font=font)) / 2, y), left, font=font, fill=(20, 20, 20))
        else:
            d.text((36, y), left, font=font, fill=(20, 20, 20))
            if right:
                d.text((w - 36 - d.textlength(right, font=font), y), right, font=font, fill=(20, 20, 20))
        y += int(size * 1.6)

    line("THE DAILY GRIND CAFE", size=30, bold=True, center=True)
    line("18 Brigade Road, Bengaluru", size=20, center=True)
    line("GSTIN 29AAGFT4321L1ZW", size=20, center=True)
    y += 14
    line("Receipt No: 88213", size=21)
    line("Date: 03/10/2026   Time: 18:42", size=21)
    line("Cashier: Priya   Table: 7", size=21)
    y += 10
    d.line([(36, y), (w - 36, y)], fill=(60, 60, 60), width=2); y += 16
    for name, qty, price in [("Cappuccino", 2, 180.00), ("Masala Chai", 1, 90.00), ("Blueberry Muffin", 2, 140.00), ("Paneer Sandwich", 1, 220.00)]:
        line(f"{name} x{qty}", f"{qty * price:,.2f}")
    d.line([(36, y), (w - 36, y)], fill=(60, 60, 60), width=2); y += 16
    line("Subtotal", "950.00")
    line("CGST 2.5%", "23.75")
    line("SGST 2.5%", "23.75")
    line("TOTAL", "₹997.50", size=27, bold=True)
    y += 10
    line("Paid by UPI  Ref 6274 1189 2201", size=19)
    y += 24
    line("Thank you! Visit again", size=21, center=True)
    img.crop((0, 0, w, y + 40)).save(path)


if __name__ == "__main__":
    pdf = OUT / "nimbus_invoice.pdf"
    invoice_pdf(pdf)
    scanned_copy(pdf, OUT / "nimbus_invoice_scan.jpg")
    receipt_png(OUT / "daily_grind_receipt.png")
    print("wrote", ", ".join(p.name for p in sorted(OUT.glob("*.*")) if p.suffix != ".py"))
