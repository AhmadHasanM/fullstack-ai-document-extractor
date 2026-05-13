import os
import logging
from PIL import Image
from typing import List, Dict

logger = logging.getLogger(__name__)


class OCRProcessor:
    """
    OCR Processor menggunakan Surya OCR.

    Support:
    - OCR halaman scan
    - Multi line text
    - Fallback aman jika model gagal load
    """

    def __init__(self, api_key: str = None):
        # api_key dipertahankan agar kompatibel
        self.detector = None
        self.recognizer = None
        self.foundation = None
        self.loaded = False

    # ------------------------------------------------ #
    # Load model                                       #
    # ------------------------------------------------ #

    def _load_model(self):
        if self.loaded:
            return

        try:
            from surya.detection import DetectionPredictor
            from surya.foundation import FoundationPredictor
            from surya.recognition import RecognitionPredictor

            logger.info(
                "[OCRProcessor] Loading Surya OCR..."
            )

            self.foundation = FoundationPredictor()

            self.detector = DetectionPredictor()

            self.recognizer = RecognitionPredictor(
                foundation_predictor=self.foundation
            )

            self.loaded = True

            logger.info(
                "[OCRProcessor] Surya OCR loaded."
            )

        except Exception as e:
            logger.error(
                f"[OCRProcessor] Failed load Surya OCR: {e}"
            )
            raise e

    # ------------------------------------------------ #
    # OCR core                                         #
    # ------------------------------------------------ #

    def _ocr_image(
        self,
        image: Image.Image
    ) -> str:

        self._load_model()

        try:
            # API Surya 0.17.x:
            # recognizer pakai detector predictor langsung
            recognition = self.recognizer(
                [image],
                det_predictor=self.detector
            )

            lines = []

            for page in recognition:
                text_lines = getattr(
                    page,
                    "text_lines",
                    []
                )

                for line in text_lines:
                    text = getattr(
                        line,
                        "text",
                        ""
                    ).strip()

                    if text:
                        lines.append(text)

            return "\n".join(lines).strip()

        except Exception as e:
            logger.error(
                f"[OCRProcessor] OCR inference error: {e}"
            )
            return ""

    # ------------------------------------------------ #
    # Public methods                                   #
    # ------------------------------------------------ #

    def process_image(
        self,
        image_path: str
    ) -> Dict:
        """OCR file gambar"""

        try:
            if not os.path.exists(image_path):
                return {
                    "text": "",
                    "confidence": "low",
                    "error": (
                        f"file not found: "
                        f"{image_path}"
                    )
                }

            image = (
                Image.open(image_path)
                .convert("RGB")
            )

            text = self._ocr_image(image)

            return {
                "text": text,
                "confidence": (
                    "high"
                    if text else "low"
                ),
                "error": None
            }

        except Exception as e:
            logger.error(
                f"[OCRProcessor] process_image error: {e}"
            )

            return {
                "text": "",
                "confidence": "low",
                "error": str(e)
            }

    def process_pdf_page(
        self,
        page_image_path: str
    ) -> Dict:
        """OCR halaman PDF hasil convert PNG"""
        return self.process_image(
            page_image_path
        )

    # ------------------------------------------------ #
    # Table extraction sederhana                       #
    # ------------------------------------------------ #

    def extract_tables_from_image(
        self,
        image_path: str
    ) -> List[Dict]:

        try:
            result = self.process_image(
                image_path
            )

            text = result.get(
                "text",
                ""
            )

            if not text.strip():
                return []

            lines = [
                line.strip()
                for line in text.split("\n")
                if line.strip()
            ]

            table_rows = []

            for line in lines:
                normalized = (
                    line.replace(
                        "\t",
                        "  "
                    )
                )

                cols = [
                    c.strip()
                    for c in normalized.split(
                        "  "
                    )
                    if c.strip()
                ]

                if len(cols) >= 2:
                    table_rows.append(cols)

            if not table_rows:
                return []

            max_cols = max(
                len(row)
                for row in table_rows
            )

            normalized_rows = []

            for row in table_rows:
                padded = row + (
                    [""] * (
                        max_cols - len(row)
                    )
                )

                normalized_rows.append(
                    padded
                )

            markdown_rows = []

            for row in normalized_rows:
                markdown_rows.append(
                    "| "
                    + " | ".join(row)
                    + " |"
                )

            separator = (
                "| "
                + " | ".join(
                    ["---"] * max_cols
                )
                + " |"
            )

            markdown_rows.insert(
                1,
                separator
            )

            return [{
                "index": 0,
                "page_number": 1,
                "method": "surya-ocr",
                "markdown": "\n".join(
                    markdown_rows
                )
            }]

        except Exception as e:
            logger.error(
                f"[OCRProcessor] "
                f"extract_tables error: {e}"
            )

            return []

    # ------------------------------------------------ #
    # Formula extraction placeholder                   #
    # ------------------------------------------------ #

    def extract_formulas(
        self,
        image_path: str
    ) -> List[str]:
        """
        Surya bukan OCR rumus khusus.
        Return kosong agar kompatibel.
        """
        return []