from __future__ import annotations
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from pypdf import PdfReader
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

try:
    import pytesseract
except Exception:  # pragma: no cover
    pytesseract = None

@dataclass
class PageExtraction:
    page: int
    text: str
    method: str
    confidence: float
    needs_review: bool
    warnings: list[str]

class TextExtractor:
    """Native PDF extraction with OCR fallback and page-level quality scoring."""
    def __init__(self, min_native_chars: int = 80, review_threshold: float = 0.72):
        self.min_native_chars = min_native_chars
        self.review_threshold = review_threshold

    @staticmethod
    def _quality(text: str) -> float:
        text = text or ""
        if not text.strip(): return 0.0
        printable = sum(ch.isprintable() for ch in text) / max(len(text), 1)
        alpha = sum(ch.isalpha() for ch in text) / max(len(text), 1)
        replacement_penalty = min(text.count("�") / max(len(text), 1) * 10, 0.5)
        return max(0.0, min(1.0, 0.45 * printable + 0.55 * min(alpha / 0.45, 1.0) - replacement_penalty))

    @staticmethod
    def preprocess_image(image: Image.Image) -> Image.Image:
        image = ImageOps.exif_transpose(image).convert("L")
        image = ImageOps.autocontrast(image)
        image = ImageEnhance.Contrast(image).enhance(1.6)
        return image.filter(ImageFilter.SHARPEN)

    def extract_pdf(self, path: str | Path) -> list[PageExtraction]:
        reader = PdfReader(str(path))
        results: list[PageExtraction] = []
        for idx, page in enumerate(reader.pages, start=1):
            warnings: list[str] = []
            native = page.extract_text() or ""
            quality = self._quality(native)
            method = "native"
            text = native
            if len(native.strip()) < self.min_native_chars or quality < self.review_threshold:
                warnings.append("Native text was sparse or low quality; OCR fallback recommended.")
                ocr_text = self._ocr_pdf_page(page)
                ocr_quality = self._quality(ocr_text)
                if ocr_quality > quality:
                    text, quality, method = ocr_text, ocr_quality, "ocr_fallback"
            needs_review = quality < self.review_threshold
            if needs_review: warnings.append("Low-confidence page requires human review or enhanced OCR retry.")
            results.append(PageExtraction(idx, text, method, quality, needs_review, warnings))
        return results

    def _ocr_pdf_page(self, page) -> str:
        if pytesseract is None: return ""
        # pypdf does not render pages. Extract embedded page images when available.
        candidates: list[str] = []
        try:
            for image_file in page.images:
                img = Image.open(io.BytesIO(image_file.data))
                candidates.append(pytesseract.image_to_string(self.preprocess_image(img)))
        except Exception:
            return ""
        return "\n".join(x for x in candidates if x.strip())

    def extract_image(self, path: str | Path) -> list[PageExtraction]:
        if pytesseract is None:
            return [PageExtraction(1, "", "ocr_unavailable", 0.0, True, ["Tesseract OCR is not installed."])]
        image = self.preprocess_image(Image.open(path))
        text = pytesseract.image_to_string(image)
        quality = self._quality(text)
        return [PageExtraction(1, text, "ocr", quality, quality < self.review_threshold,
                               [] if quality >= self.review_threshold else ["Low-confidence image OCR."])]

    def extract(self, path: str | Path) -> list[PageExtraction]:
        path = Path(path)
        if path.suffix.lower() == ".pdf": return self.extract_pdf(path)
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}: return self.extract_image(path)
        text = path.read_text(encoding="utf-8", errors="replace")
        quality = self._quality(text)
        return [PageExtraction(1, text, "text", quality, quality < self.review_threshold, [])]
