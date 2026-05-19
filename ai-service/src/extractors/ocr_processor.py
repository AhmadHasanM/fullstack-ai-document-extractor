"""
OCR Processor — thin wrapper around DeepSeek OCR2 Local Service.
Backward compatible dengan interface lama (Surya OCR).

Semua inference lokal via GPU/CPU, tidak ada cloud API.
"""

import os
import logging
from typing import List, Dict

import numpy as np
from PIL import Image

from ..services.deepseek_ocr_service import (
    DeepSeekOCRService,
    DeepSeekOCRConfig,
    prepare_image_for_ocr,
    normalize_easyocr_result,
)

logger = logging.getLogger(__name__)


class OCRProcessor:
    """
    OCR Processor — menggunakan DeepSeek OCR2 lokal di belakang layar.

    Interface backward-compatible dengan OCRProcessor lama.
    Semua inference GPU-first dengan fallback CPU.
    """

    def __init__(self, api_key: str = None):
        self.api_key = api_key
        config = DeepSeekOCRConfig(
            device="cuda" if __import__("torch").cuda.is_available() else "cpu",
        )
        self._service = DeepSeekOCRService(config)
        self._pdf_path = None

    def set_pdf_path(self, pdf_path: str):
        self._pdf_path = pdf_path

    def _ocr_pil_image(self, pil_img: Image.Image, page_number: int = 1) -> Dict:
        """
        OCR langsung dari PIL Image tanpa melalui fitz.

        1. PIL.Image → numpy.ndarray
        2. Validasi + konversi (grayscale/RGBA → RGB)
        3. EasyOCR reader.readtext()
        """
        reader = self._service._get_ocr_reader()

        # Convert PIL → numpy → validasi
        img_array = np.array(pil_img.convert("RGB"))
        ocr_input = prepare_image_for_ocr(img_array, f"direct image page {page_number}")

        results = reader.readtext(
            ocr_input,
            paragraph=True,
            width_ths=0.7,
            height_ths=0.7,
        )

        blocks = []
        full_text_parts = []
        total_confidence = 0.0

        for result in results:
            bbox, text, confidence = normalize_easyocr_result(result)

            if not text or not text.strip():
                continue

            if bbox is not None:
                x_coords = [p[0] for p in bbox]
                y_coords = [p[1] for p in bbox]
                bbox_out = [
                    round(min(x_coords), 2),
                    round(min(y_coords), 2),
                    round(max(x_coords), 2),
                    round(max(y_coords), 2),
                ]
            else:
                bbox_out = [0, 0, 0, 0]

            conf_value = round(float(confidence), 4) if confidence is not None else None

            blocks.append({
                "type": "text",
                "bbox": bbox_out,
                "content": text.strip(),
                "confidence": conf_value,
            })
            full_text_parts.append(text.strip())
            if confidence is not None:
                total_confidence += float(confidence)

        avg_confidence = total_confidence / len(blocks) if blocks else 0.0

        return {
            "text": "\n".join(full_text_parts),
            "blocks": blocks,
            "confidence": round(avg_confidence, 4),
        }

    def process_image(self, image_path: str) -> Dict:
        """OCR satu file gambar via DeepSeek OCR2."""
        try:
            if not os.path.exists(image_path):
                return {"text": "", "confidence": "low",
                        "error": f"file not found: {image_path}"}

            if image_path.lower().endswith(".pdf"):
                import fitz
                doc = fitz.open(image_path)
                page = doc[0]
                result = self._service._ocr_page_image(page, 1)
                doc.close()
            else:
                img = Image.open(image_path).convert("RGB")
                result = self._ocr_pil_image(img, 1)

            text = result.get("text", "")
            confidence = result.get("confidence", 0)

            return {
                "text": text,
                "confidence": "high" if confidence > 0.5 else "medium",
                "error": None,
                "blocks": result.get("blocks", []),
            }

        except Exception as e:
            logger.error(f"[OCRProcessor] process_image error: {e}")
            return {"text": "", "confidence": "low", "error": str(e)}

    def process_pdf_page(self, page_image_path: str) -> Dict:
        """OCR halaman PDF dari file gambar PNG."""
        return self.process_image(page_image_path)

    def extract_tables_from_image(self, image_path: str) -> List[Dict]:
        """Ekstrak tabel dari gambar via DeepSeek OCR2."""
        try:
            blocks = self._service._detect_tables_from_blocks(
                self._load_blocks_from_image(image_path), page_number=1
            )
            return blocks
        except Exception as e:
            logger.error(f"[OCRProcessor] extract_tables error: {e}")
            return []

    def _load_blocks_from_image(self, image_path: str) -> List[Dict]:
        result = self.process_image(image_path)
        return result.get("blocks", [])

    def extract_formulas(self, image_path: str) -> List[str]:
        return []

    @property
    def service(self) -> DeepSeekOCRService:
        return self._service
