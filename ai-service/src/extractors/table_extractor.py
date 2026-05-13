import fitz
import pdfplumber
import torch
import numpy as np
import logging
from PIL import Image
from typing import List, Dict, Optional, Tuple
from transformers import TableTransformerForObjectDetection, DetrImageProcessor

logger = logging.getLogger(__name__)


class TableExtractor:
    """
    Ekstrak tabel dari PDF menggunakan dua strategi:
    1. Table Transformer (Microsoft) — untuk PDF dengan tabel berbasis gambar / layout kompleks
    2. pdfplumber — sebagai fallback untuk tabel digital sederhana
    """

    DETECTION_MODEL = "microsoft/table-transformer-detection"
    STRUCTURE_MODEL = "microsoft/table-transformer-structure-recognition"

    # Label dari structure recognition model
    STRUCTURE_LABELS = {
        0: "table",
        1: "table column",
        2: "table row",
        3: "table column header",
        4: "table projected row header",
        5: "table spanning cell",
        6: "no object",
    }

    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"[TableExtractor] Device: {self.device}")

        self._detection_model = None
        self._structure_model = None
        self._processor = None

    def _load_models(self):
        """Lazy load model agar tidak berat saat startup"""
        if self._detection_model is None:
            logger.info("[TableExtractor] Loading Table Transformer models...")
            self._processor = DetrImageProcessor.from_pretrained(self.DETECTION_MODEL)
            self._detection_model = TableTransformerForObjectDetection.from_pretrained(
                self.DETECTION_MODEL
            ).to(self.device)
            self._structure_model = TableTransformerForObjectDetection.from_pretrained(
                self.STRUCTURE_MODEL
            ).to(self.device)
            logger.info("[TableExtractor] Models loaded.")

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def extract_tables(self) -> List[Dict]:
        """Entry point: ekstrak semua tabel dari seluruh halaman PDF"""
        raise NotImplementedError(
            "Gunakan extract_tables_from_pdf(pdf_path) sebagai gantinya."
        )

    def extract_tables_from_pdf(self, pdf_path: str, dpi: int = 200) -> List[Dict]:
        """
        Ekstrak tabel dari semua halaman PDF.
        Mencoba Table Transformer dulu; fallback ke pdfplumber jika gagal.
        """
        self._load_models()
        doc = fitz.open(pdf_path)
        all_tables = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            page_label = page_num + 1

            try:
                tables = self._extract_page_transformer(page, page_label, dpi)
                if not tables:
                    # Tidak ada tabel terdeteksi → coba pdfplumber
                    tables = self._extract_page_pdfplumber(pdf_path, page_label)
            except Exception as e:
                logger.warning(
                    f"[TableExtractor] Transformer gagal halaman {page_label}: {e}. "
                    "Fallback ke pdfplumber."
                )
                tables = self._extract_page_pdfplumber(pdf_path, page_label)

            all_tables.extend(tables)

        doc.close()
        return all_tables

    # ------------------------------------------------------------------ #
    #  Strategy 1: Table Transformer                                       #
    # ------------------------------------------------------------------ #

    def _page_to_image(self, page: fitz.Page, dpi: int) -> Image.Image:
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    def _detect_tables(self, image: Image.Image, threshold: float = 0.65) -> List[Dict]:
        """Deteksi lokasi tabel dalam gambar halaman"""
        inputs = self._processor(images=image, return_tensors="pt").to(self.device)
        with torch.no_grad():
            outputs = self._detection_model(**inputs)

        target_sizes = torch.tensor([image.size[::-1]])
        results = self._processor.post_process_object_detection(
            outputs, target_sizes=target_sizes, threshold=threshold
        )[0]

        tables = []
        for score, label, box in zip(
            results["scores"], results["labels"], results["boxes"]
        ):
            if label.item() == 0:  # class 0 = table
                x1, y1, x2, y2 = map(int, box.tolist())
                tables.append({
                    "bbox": (x1, y1, x2, y2),
                    "confidence": float(score),
                    "image": image.crop((x1, y1, x2, y2)),
                })
        return tables

    def _recognize_structure(
        self, table_image: Image.Image, threshold: float = 0.6
    ) -> Tuple[List, List]:
        """
        Kenali struktur tabel (baris & kolom) menggunakan structure recognition model.
        Return: (row_boxes, col_boxes)
        """
        inputs = self._processor(images=table_image, return_tensors="pt").to(self.device)
        with torch.no_grad():
            outputs = self._structure_model(**inputs)

        target_sizes = torch.tensor([table_image.size[::-1]])
        results = self._processor.post_process_object_detection(
            outputs, target_sizes=target_sizes, threshold=threshold
        )[0]

        rows, cols = [], []
        for score, label, box in zip(
            results["scores"], results["labels"], results["boxes"]
        ):
            label_name = self.STRUCTURE_LABELS.get(label.item(), "unknown")
            box_vals = box.tolist()
            if label_name == "table row":
                rows.append(box_vals)
            elif label_name == "table column":
                cols.append(box_vals)

        # Urutkan baris dari atas ke bawah, kolom dari kiri ke kanan
        rows.sort(key=lambda b: b[1])
        cols.sort(key=lambda b: b[0])
        return rows, cols

    def _crop_cell(
        self,
        table_image: Image.Image,
        row_box: List[float],
        col_box: List[float],
    ) -> Image.Image:
        """Potong satu sel dari perpotongan baris & kolom"""
        x1 = max(col_box[0], 0)
        y1 = max(row_box[1], 0)
        x2 = min(col_box[2], table_image.width)
        y2 = min(row_box[3], table_image.height)
        return table_image.crop((x1, y1, x2, y2))

    def _image_to_text(self, cell_image: Image.Image) -> str:
        """OCR satu sel menggunakan pytesseract"""
        try:
            import pytesseract
            text = pytesseract.image_to_string(
                cell_image, config="--psm 6 --oem 3"
            ).strip()
            return text.replace("\n", " ")
        except Exception:
            return ""

    def _build_table_data(
        self,
        table_image: Image.Image,
        rows: List,
        cols: List,
    ) -> List[List[str]]:
        """Bangun data tabel 2D dari baris & kolom"""
        table_data = []
        for row_box in rows:
            row_data = []
            for col_box in cols:
                cell_img = self._crop_cell(table_image, row_box, col_box)
                text = self._image_to_text(cell_img)
                row_data.append(text)
            table_data.append(row_data)
        return table_data

    def _extract_page_transformer(
        self, page: fitz.Page, page_label: int, dpi: int
    ) -> List[Dict]:
        """Ekstrak tabel dari satu halaman menggunakan Table Transformer"""
        image = self._page_to_image(page, dpi)
        detected = self._detect_tables(image)

        results = []
        for idx, table_info in enumerate(detected):
            table_img = table_info["image"]
            rows, cols = self._recognize_structure(table_img)

            if not rows or not cols:
                logger.debug(
                    f"[TableExtractor] Halaman {page_label} tabel {idx}: "
                    "struktur tidak terdeteksi, skip."
                )
                continue

            table_data = self._build_table_data(table_img, rows, cols)

            if not table_data:
                continue

            results.append(self._build_result(table_data, page_label, idx, "transformer"))

        return results

    # ------------------------------------------------------------------ #
    #  Strategy 2: pdfplumber fallback                                    #
    # ------------------------------------------------------------------ #

    def _extract_page_pdfplumber(self, pdf_path: str, page_label: int) -> List[Dict]:
        """Fallback: ekstrak tabel dengan pdfplumber"""
        results = []
        try:
            with pdfplumber.open(pdf_path) as pdf:
                page = pdf.pages[page_label - 1]
                tables = page.extract_tables({
                    "vertical_strategy": "lines",
                    "horizontal_strategy": "lines",
                    "intersection_tolerance": 5,
                })
                if not tables:
                    # Coba strategi looser
                    tables = page.extract_tables({
                        "vertical_strategy": "text",
                        "horizontal_strategy": "text",
                        "intersection_tolerance": 10,
                    })
                for idx, table in enumerate(tables or []):
                    if table and len(table) > 1:
                        results.append(
                            self._build_result(table, page_label, idx, "pdfplumber")
                        )
        except Exception as e:
            logger.warning(f"[TableExtractor] pdfplumber error halaman {page_label}: {e}")
        return results

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    def _build_result(
        self,
        table_data: List[List[str]],
        page_number: int,
        table_index: int,
        method: str,
    ) -> Dict:
        """Bangun dict hasil ekstraksi tabel"""
        # Bersihkan None
        cleaned = [
            [str(cell).strip() if cell is not None else "" for cell in row]
            for row in table_data
        ]

        # Pastikan semua baris punya panjang yang sama
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

    def _to_markdown(self, table: List[List[str]]) -> str:
        if not table:
            return ""

        def escape(cell: str) -> str:
            return cell.replace("|", "\\|").replace("\n", " ")

        lines = []
        headers = table[0]
        lines.append("| " + " | ".join(escape(h) for h in headers) + " |")
        lines.append("| " + " | ".join("---" for _ in headers) + " |")
        for row in table[1:]:
            lines.append("| " + " | ".join(escape(c) for c in row) + " |")
        return "\n".join(lines)

    def _to_csv(self, table: List[List[str]]) -> str:
        import csv
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerows(table)
        return output.getvalue()