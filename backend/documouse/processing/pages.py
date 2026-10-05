"""Turn an upload into page images.

The same images are fed to the document engine and shown in the review viewer,
so every coordinate the engine reports lines up exactly with what the user sees.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageOps

SUPPORTED_TYPES = {
    "application/pdf": "pdf",
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "image/tiff": "tiff",
    "image/bmp": "bmp",
}


class UnsupportedFile(ValueError):
    pass


@dataclass
class PageImage:
    index: int
    image: Image.Image  # RGB


def sniff_content_type(data: bytes) -> str | None:
    """Identify the file from its bytes rather than trusting the extension."""
    if data.startswith(b"%PDF"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:4] in (b"II*\x00", b"MM\x00*"):
        return "image/tiff"
    if data[:2] == b"BM":
        return "image/bmp"
    return None


def render_pages(data: bytes, content_type: str, *, dpi: int, max_pages: int) -> list[PageImage]:
    if content_type == "application/pdf":
        return _render_pdf(data, dpi=dpi, max_pages=max_pages)
    if content_type in SUPPORTED_TYPES:
        return _load_image(data, max_pages=max_pages)
    raise UnsupportedFile(content_type)


def _render_pdf(data: bytes, *, dpi: int, max_pages: int) -> list[PageImage]:
    import pypdfium2 as pdfium

    try:
        pdf = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as exc:  # encrypted or corrupt
        raise UnsupportedFile("This PDF couldn't be opened. It may be password-protected or damaged.") from exc
    pages: list[PageImage] = []
    try:
        for index in range(min(len(pdf), max_pages)):
            page = pdf[index]
            bitmap = page.render(scale=dpi / 72)
            pages.append(PageImage(index=index, image=bitmap.to_pil().convert("RGB")))
            page.close()
    finally:
        pdf.close()
    if not pages:
        raise UnsupportedFile("This PDF has no pages.")
    return pages


def _load_image(data: bytes, *, max_pages: int) -> list[PageImage]:
    try:
        img = Image.open(io.BytesIO(data))
    except Exception as exc:
        raise UnsupportedFile("This image couldn't be opened.") from exc
    pages: list[PageImage] = []
    # Multi-frame TIFFs are common for scanned documents.
    for index in range(min(getattr(img, "n_frames", 1), max_pages)):
        img.seek(index)
        # Phone photos store rotation in EXIF; apply it so the page is upright.
        frame = ImageOps.exif_transpose(img.copy()) or img.copy()
        pages.append(PageImage(index=index, image=frame.convert("RGB")))
    return pages


def encode_jpeg(image: Image.Image, quality: int = 88) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()
