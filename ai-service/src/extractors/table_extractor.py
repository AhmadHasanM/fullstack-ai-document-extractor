"""
Table Extractor — lokal, tanpa model transformers.

Strategi:
1. pdfplumber untuk PDF digital (line/text-based)
2. DeepSeek OCR2 layout analysis untuk scanned PDF

Semua inference lokal via GPU/CPU.
"""

import logging
from typing import List, Dict

import pdfplumber

from ..services.deepseek_ocr_service import DeepSeekOCRService, DeepSeekOCRConfig

logger = logging.getLogger(__name__)


class TableExtractor:
    """
    Ekstrak tabel dari PDF tanpa transformers / cloud API.

    Digital PDF → pdfplumber (line/text strategy)
    Scanned PDF → DeepSeek OCR2 heuristic blocks
    """

    def __init__(self):
        config = DeepSeekOCRConfig()
        self._ocr_service = DeepSeekOCRService(config)

    def extract_tables_from_pdf(self, pdf_path: str) -> List[Dict]:
        """
        Ekstrak tabel dari semua halaman PDF.
        Digital → pdfplumber langsung.
        Fallback → DeepSeek OCR2 layout heuristic.
        """
        all_tables = []
        pages_processed = set()

        # Strategy 1: pdfplumber untuk digital tables
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages):
                    page_number = page_num + 1

                    tables = self._extract_with_pdfplumber(page)
                    if tables:
                        all_tables.extend(tables)
                        pages_processed.add(page_number)

        except Exception as e:
            logger.warning(f"[TableExtractor] pdfplumber error: {e}")

        # Strategy 2: DeepSeek OCR heuristic fallback
        try:
            import fitz
            doc = fitz.open(pdf_path)

            for page_num in range(len(doc)):
                page_number = page_num + 1
                if page_number in pages_processed:
                    continue

                page = doc[page_num]
                blocks = self._ocr_service._extract_blocks_from_page(page)
                tables = self._ocr_service._detect_tables_from_blocks(
                    blocks, page_number
                )
                if tables:
                    all_tables.extend(tables)
                    logger.info(
                        f"[TableExtractor] OCR fallback: {len(tables)} table(s) "
                        f"on page {page_number}"
                    )

            doc.close()
        except Exception as e:
            logger.warning(f"[TableExtractor] OCR fallback error: {e}")

        return all_tables

    def _extract_with_pdfplumber(self, page) -> List[Dict]:
        """Extract tables from a single pdfplumber page."""
        results = []

        # Try line strategy first
        tables = page.extract_tables({
            "vertical_strategy": "lines",
            "horizontal_strategy": "lines",
            "intersection_tolerance": 5,
        })

        if not tables:
            tables = page.extract_tables({
                "vertical_strategy": "text",
                "horizontal_strategy": "text",
                "intersection_tolerance": 10,
            })

        for idx, table in enumerate(tables or []):
            if not table or len(table) < 2:
                continue

            results.append(self._build_result(table, page.page_number, idx, "pdfplumber"))

        return results

    def _build_result(
        self, table_data: List[List[str]], page_number: int,
        table_index: int, method: str
    ) -> Dict:
        cleaned = [
            [str(cell).strip() if cell is not None else "" for cell in row]
            for row in table_data
        ]

        max_cols = max((len(r) for r in cleaned), default=0)
        cleaned = [r + [""] * (max_cols - len(r)) for r in cleaned]

        headers = cleaned[0] if cleaned else []
        rows = cleaned[1:] if len(cleaned) > 1 else []

        return {
            "page_number": page_number,
            "table_index": table_index,
            "method": method,
            "headers": headers,
            "rows": rows,
            "markdown": self._to_markdown(cleaned),
            "csv": self._to_csv(cleaned),
        }

    @staticmethod
    def _to_markdown(table: List[List[str]]) -> str:
        if not table:
            return ""

        def escape(cell: str) -> str:
            return cell.replace("|", "\\|").replace("\n", " ")

        lines = []
        lines.append("| " + " | ".join(escape(c) for c in table[0]) + " |")
        lines.append("| " + " | ".join("---" for _ in table[0]) + " |")
        for row in table[1:]:
            lines.append("| " + " | ".join(escape(c) for c in row) + " |")
        return "\n".join(lines)

    @staticmethod
    def _to_csv(table: List[List[str]]) -> str:
        import csv
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerows(table)
        return output.getvalue()
