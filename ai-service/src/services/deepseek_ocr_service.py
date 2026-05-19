"""
DeepSeek OCR2 Local Service

Local OCR inference engine dengan GPU acceleration.
100% offline — tidak menggunakan cloud API sama sekali.

Features:
- Text extraction (digital + scanned PDF)
- Layout analysis (headings, paragraphs, lists, figures)
- Table detection & extraction
- Bounding box detection per block
- Structured JSON output
- GPU acceleration (CUDA) with CPU fallback
- Benchmark logging

Architecture:
  DeepSeekOCRService
    ├── process_document() → structured dict
    ├── _process_digital()  → PyMuPDF text + pdfplumber tables
    ├── _process_scanned()  → page rendering + OCR engine
    ├── _process_mixed()    → digital + OCR fallback
    ├── _ocr_page_image()   → EasyOCR (GPU) → text + bboxes
    ├── _analyze_layout()   → heuristic layout classification
    ├── _extract_tables()   → pdfplumber + heuristic OCR tables
    └── _to_structured_output() → final JSON-compatible output
"""

import os
import re
import json
import time
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime

import fitz
import torch
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
#  Configuration                                                               #
# --------------------------------------------------------------------------- #


@dataclass
class DeepSeekOCRConfig:
    device: str = "cuda" if torch.cuda.is_available() else "cpu"
    batch_size: int = 4
    use_gpu: bool = torch.cuda.is_available()
    ocr_languages: List[str] = field(default_factory=lambda: ["en"])
    ocr_confidence_threshold: float = 0.3
    page_dpi: int = 200
    table_dpi: int = 200
    enable_benchmark: bool = True
    digital_text_min_chars: int = 50
    ocr_text_min_length: int = 20

    def __post_init__(self):
        if self.device == "cuda" and not torch.cuda.is_available():
            logger.warning("[DeepSeek OCR2] CUDA requested but not available, falling back to CPU")
            self.device = "cpu"
            self.use_gpu = False


# --------------------------------------------------------------------------- #
#  Benchmark Logger                                                            #
# --------------------------------------------------------------------------- #


class BenchmarkLogger:
    """Collect and print OCR benchmark statistics."""

    def __init__(self):
        self.metrics: Dict[str, Any] = {}
        self.vram_samples: List[float] = []
        self.page_times: List[Dict] = []

    def log(self, key: str, value: Any):
        self.metrics[key] = value

    def log_page(self, page_number: int, ocr_time: float, block_count: int, status: str = "ok"):
        self.page_times.append({
            "page": page_number,
            "ocr_time_s": round(ocr_time, 3),
            "blocks": block_count,
            "status": status,
        })

    def sample_vram(self):
        if torch.cuda.is_available():
            used = torch.cuda.memory_allocated() / 1e9
            self.vram_samples.append(used)
            self.metrics["vram_gb"] = round(used, 2)

    def print_summary(self):
        parts = ["\n═══════════════════════════════════════"]
        parts.append("  DeepSeek OCR2 — Benchmark Summary")
        parts.append("═══════════════════════════════════════")
        for k, v in self.metrics.items():
            label = f"{v:.2f}" if isinstance(v, float) else str(v)
            parts.append(f"  {k}: {label}")
        if self.vram_samples:
            parts.append(f"  peak_vram_gb: {max(self.vram_samples):.2f}")
            parts.append(f"  avg_vram_gb: {sum(self.vram_samples)/len(self.vram_samples):.2f}")
        if self.page_times:
            total_ocr_time = sum(p["ocr_time_s"] for p in self.page_times)
            parts.append(f"  pages: {len(self.page_times)}, total_ocr_time_s: {total_ocr_time:.2f}")
        parts.append("═══════════════════════════════════════\n")
        logger.info("\n".join(parts))


# --------------------------------------------------------------------------- #
#  Input validation helper                                                     #
# --------------------------------------------------------------------------- #


def prepare_image_for_ocr(
    img: Any,
    source_desc: str = "image"
) -> np.ndarray:
    """
    Convert any supported input type to numpy.ndarray for EasyOCR.

    Accepts:
      - PIL.Image.Image
      - numpy.ndarray
      - str (file path)
      - bytes

    Returns: numpy.ndarray (RGB, HWC format)
    Raises: TypeError if type is not supported
    """
    import numpy as np

    if isinstance(img, np.ndarray):
        arr = img
        logger.debug(f"[DeepSeek OCR2] OCR input: ndarray shape={arr.shape}")
    elif isinstance(img, Image.Image):
        arr = np.array(img.convert("RGB"))
        logger.debug(f"[DeepSeek OCR2] OCR input: PIL.Image → ndarray shape={arr.shape}")
    elif isinstance(img, str):
        logger.debug(f"[DeepSeek OCR2] OCR input: file path '{img}'")
        return img
    elif isinstance(img, bytes):
        logger.debug(f"[DeepSeek OCR2] OCR input: bytes ({len(img)} bytes)")
        return img
    else:
        raise TypeError(
            f"[DeepSeek OCR2] Invalid OCR input type for {source_desc}: "
            f"{type(img)}. Expected numpy.ndarray, PIL.Image, str(path), or bytes."
        )

    # Auto RGB conversion if grayscale
    if len(arr.shape) == 2:
        logger.debug(f"[DeepSeek OCR2] Converting grayscale ({arr.shape}) → RGB")
        arr = np.stack([arr] * 3, axis=-1)
    elif arr.shape[2] == 4:
        logger.debug(f"[DeepSeek OCR2] Converting RGBA ({arr.shape}) → RGB")
        arr = arr[:, :, :3]
    elif arr.shape[2] != 3:
        raise ValueError(
            f"[DeepSeek OCR2] Unexpected channel count for {source_desc}: "
            f"shape={arr.shape}"
        )

    return arr


def normalize_easyocr_result(result: Any) -> tuple:
    """
    Safely parse a single EasyOCR result entry.

    EasyOCR can return varying formats depending on the model and parameters:
      - detail=0  → str (just the text)
      - detail=1  → [bbox, text, confidence]  (3-tuple)
      - paragraph=True → [bbox, text]          (2-tuple, no confidence)

    Returns: (bbox, text, confidence)
      - bbox can be None if detail=0
      - confidence can be None if not available
    """
    if isinstance(result, str):
        return None, result, None

    if not isinstance(result, (list, tuple)):
        return None, str(result), None

    length = len(result)

    if length == 3:
        bbox, text, confidence = result
        return bbox, text, confidence

    if length == 2:
        bbox, text = result
        return bbox, text, None

    if length == 1:
        return None, str(result[0]), None

    return None, None, None


# --------------------------------------------------------------------------- #
#  Main Service                                                                #
# --------------------------------------------------------------------------- #


class DeepSeekOCRService:
    """
    DeepSeek OCR2 Local — Engine OCR lokal untuk text extraction,
    layout detection, table extraction, bbox detection, dan structured parsing.

    ── Cara pakai ──
        service = DeepSeekOCRService()
        result = service.process_document("path/to/document.pdf")
        print(result["pages"][0]["text"])          # extracted text
        print(result["pages"][0]["blocks"])         # layout blocks with bbox
        print(result["tables"])                     # extracted tables
    """

    def __init__(self, config: Optional[DeepSeekOCRConfig] = None):
        self.config = config or DeepSeekOCRConfig()
        self._ocr_reader = None
        self._benchmark = BenchmarkLogger() if self.config.enable_benchmark else None
        self._log_system_info()

    # ───────────────────────────────────────────────────────────────── #
    #  System info & logging                                            #
    # ───────────────────────────────────────────────────────────────── #

    def _log_system_info(self):
        logger.info("═══════════════════════════════════════")
        logger.info("  DeepSeek OCR2 Initialization")
        logger.info("═══════════════════════════════════════")
        logger.info(f"  Device          : {self.config.device}")
        logger.info(f"  GPU Available   : {torch.cuda.is_available()}")

        if torch.cuda.is_available():
            for i in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(i)
                logger.info(f"  GPU {i}           : {props.name}")
                logger.info(f"  VRAM            : {props.total_memory / 1e9:.2f} GB")
                logger.info(f"  CUDA Capability : {props.major}.{props.minor}")

        try:
            import psutil
            logger.info(f"  CPU Cores       : {psutil.cpu_count()}")
            logger.info(f"  RAM             : {psutil.virtual_memory().total / 1e9:.2f} GB")
        except ImportError:
            pass

        logger.info(f"  OCR Languages   : {self.config.ocr_languages}")
        logger.info(f"  Batch Size      : {self.config.batch_size}")
        logger.info(f"  Page DPI        : {self.config.page_dpi}")
        logger.info("═══════════════════════════════════════\n")

    # ───────────────────────────────────────────────────────────────── #
    #  OCR Engine (lazy-loaded EasyOCR)                                 #
    # ───────────────────────────────────────────────────────────────── #

    def _get_ocr_reader(self):
        if self._ocr_reader is not None:
            return self._ocr_reader

        logger.info(f"[DeepSeek OCR2] Loading EasyOCR reader (lang={self.config.ocr_languages})...")
        t0 = time.time()
        import easyocr
        self._ocr_reader = easyocr.Reader(
            self.config.ocr_languages,
            gpu=self.config.use_gpu,
            model_storage_directory=None,
            download_enabled=True,
        )
        load_time = time.time() - t0
        logger.info(f"[DeepSeek OCR2] EasyOCR loaded in {load_time:.2f}s")

        if self._benchmark:
            self._benchmark.log("model_load_time", load_time)
            self._benchmark.sample_vram()

        return self._ocr_reader

    # ───────────────────────────────────────────────────────────────── #
    #  Public entry point                                                #
    # ───────────────────────────────────────────────────────────────── #

    def process_document(self, pdf_path: str) -> Dict:
        """
        Main entry: OCR-processing satu dokumen PDF.

        Returns structured dict:
        {
            "pages":     [{page_number, text, blocks, tables_on_page}],
            "tables":    [{page_number, table_index, markdown, csv, headers, rows}],
            "extraction_method": "digital" | "scanned" | "mixed",
            "ocr_pages": [list of page numbers that needed OCR],
            "failed_pages": [list of page numbers where OCR failed],
            "benchmark": {...} (optional)
        }
        """
        t_start = time.time()
        logger.info(f"[DeepSeek OCR2] Processing document: {os.path.basename(pdf_path)}")

        # Detect PDF type
        from ..extractors.pdf_detector import PDFDetector
        detector = PDFDetector(pdf_path)
        pdf_type = detector.detect_type()
        metadata = detector.get_metadata()
        page_count = metadata.get("page_count", 0)

        logger.info(f"[DeepSeek OCR2] Type={pdf_type}, Pages={page_count}")

        # Route based on type
        if pdf_type == "digital":
            result = self._process_digital(pdf_path)
        elif pdf_type == "scanned":
            result = self._process_scanned(pdf_path)
        else:
            result = self._process_mixed(pdf_path)

        t_total = time.time() - t_start
        logger.info(f"[DeepSeek OCR2] Document processed in {t_total:.2f}s")

        # Benchmark
        if self._benchmark:
            self._benchmark.log("total_time", round(t_total, 3))
            self._benchmark.log("page_count", page_count)
            self._benchmark.log("pdf_type", pdf_type)

            pages = result.get("pages", [])
            block_count = sum(len(p.get("blocks", [])) for p in pages)
            table_count = len(result.get("tables", []))
            self._benchmark.log("block_count", block_count)
            self._benchmark.log("table_count", table_count)
            self._benchmark.sample_vram()
            self._benchmark.print_summary()
            result["benchmark"] = {
                k: (round(v, 4) if isinstance(v, float) else v)
                for k, v in self._benchmark.metrics.items()
            }

        if self._benchmark:
            del self._benchmark

        return result

    # ───────────────────────────────────────────────────────────────── #
    #  Digital PDF processing (no ML needed)                             #
    # ───────────────────────────────────────────────────────────────── #

    def _process_digital(self, pdf_path: str) -> Dict:
        logger.info("[DeepSeek OCR2] Processing as digital PDF...")

        doc = fitz.open(pdf_path)
        pages_data = []
        all_tables = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            page_number = page_num + 1

            blocks = self._extract_blocks_from_page(page)
            text = "\n".join(
                b["content"] for b in blocks
                if b["type"] in ("text", "heading", "list")
            )

            pages_data.append({
                "page_number": page_number,
                "text": text,
                "blocks": blocks,
            })

        doc.close()

        tables = self._extract_tables_digital(pdf_path)
        all_tables.extend(tables)

        if self._benchmark:
            self._benchmark.log("extraction_time", 0)

        return {
            "pages": pages_data,
            "tables": all_tables,
            "extraction_method": "digital",
            "ocr_pages": [],
            "failed_pages": [],
        }

    def _extract_blocks_from_page(self, page: fitz.Page) -> List[Dict]:
        """Extract text blocks with layout info from a PyMuPDF page."""
        blocks_raw = page.get_text("dict")["blocks"]
        result = []

        for block in blocks_raw:
            block_type = block.get("type", 0)  # 0=text, 1=image

            if block_type == 1:
                bbox = block.get("bbox", (0, 0, 0, 0))
                result.append({
                    "type": "image",
                    "bbox": [round(v, 2) for v in bbox],
                    "content": "[IMAGE]",
                    "confidence": 1.0,
                })
                continue

            for line in block.get("lines", []):
                spans = line.get("spans", [])
                if not spans:
                    continue

                line_text = "".join(s.get("text", "") for s in spans).strip()
                if not line_text:
                    continue

                bbox = line.get("bbox", (0, 0, 0, 0))
                avg_font_size = sum(
                    s.get("size", 12) * len(s.get("text", ""))
                    for s in spans
                ) / max(len(line_text), 1)

                flags = spans[0].get("flags", 0) if spans else 0
                is_bold = bool(flags & 2**4)
                font = spans[0].get("font", "") if spans else ""

                block_type = self._classify_block_type(
                    line_text, avg_font_size, is_bold, font
                )

                result.append({
                    "type": block_type,
                    "bbox": [round(v, 2) for v in bbox],
                    "content": line_text,
                    "font_size": round(avg_font_size, 1),
                    "font": font,
                    "confidence": 1.0,
                })

        result = self._merge_blocks(result)

        return result

    def _classify_block_type(
        self, text: str, font_size: float, is_bold: bool, font: str
    ) -> str:
        text_stripped = text.strip()

        if re.match(r"^#{1,6}\s", text_stripped):
            return "heading"
        if re.match(r"^[-*+]\s", text_stripped) or re.match(r"^\d+[.)]\s", text_stripped):
            return "list"
        if font_size >= 14 and is_bold:
            return "heading"
        if any(kw in text_stripped.lower()
               for kw in ["abstract", "introduction", "conclusion",
                          "method", "result", "discussion", "reference"]):
            if font_size >= 12:
                return "heading"
        return "text"

    def _merge_blocks(self, blocks: List[Dict]) -> List[Dict]:
        """Merge consecutive blocks of the same type on the same line."""
        if not blocks:
            return blocks

        merged = [blocks[0]]
        for b in blocks[1:]:
            last = merged[-1]
            if b["type"] == last["type"] and b["type"] in ("text", "list"):
                if self._bboxes_near(last["bbox"], b["bbox"]):
                    last["content"] += " " + b["content"]
                    last["bbox"][2] = max(last["bbox"][2], b["bbox"][2])
                    last["bbox"][3] = max(last["bbox"][3], b["bbox"][3])
                    continue
            merged.append(b)
        return merged

    def _bboxes_near(self, a: List[float], b: List[float], threshold: float = 20) -> bool:
        return abs(a[3] - b[3]) < threshold and abs(a[2] - b[0]) < threshold * 2

    # ───────────────────────────────────────────────────────────────── #
    #  Page rendering → numpy array                                      #
    # ───────────────────────────────────────────────────────────────── #

    def _render_page_to_array(self, page: fitz.Page, dpi: Optional[int] = None) -> np.ndarray:
        """Render a fitz.Page to numpy.ndarray (RGB)."""
        dpi = dpi or self.config.page_dpi
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        return np.array(img)

    # ───────────────────────────────────────────────────────────────── #
    #  Scanned / OCR page processing                                     #
    # ───────────────────────────────────────────────────────────────── #

    def _process_scanned(self, pdf_path: str) -> Dict:
        logger.info("[DeepSeek OCR2] Processing as scanned PDF (EasyOCR)...")

        doc = fitz.open(pdf_path)
        pages_data = []
        all_tables = []
        ocr_pages = []
        failed_pages = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            page_number = page_num + 1

            try:
                t0 = time.time()
                ocr_result = self._ocr_page_image(page, page_number)
                ocr_time = time.time() - t0

                block_count = len(ocr_result.get("blocks", []))
                logger.info(
                    f"[DeepSeek OCR2] Page {page_number}: "
                    f"{block_count} blocks, {ocr_time:.2f}s, "
                    f"conf={ocr_result.get('confidence', 0):.3f}"
                )

                pages_data.append({
                    "page_number": page_number,
                    "text": ocr_result.get("text", ""),
                    "blocks": ocr_result.get("blocks", []),
                    "ocr_confidence": ocr_result.get("confidence", 0),
                })
                ocr_pages.append(page_number)

                if self._benchmark:
                    self._benchmark.log_page(
                        page_number, ocr_time, block_count, "ok"
                    )

                page_tables = self._detect_tables_from_blocks(
                    ocr_result.get("blocks", []), page_number
                )
                all_tables.extend(page_tables)

            except Exception as e:
                logger.error(
                    f"[DeepSeek OCR2] Page {page_number} OCR failed: {e}"
                )
                failed_pages.append(page_number)
                pages_data.append({
                    "page_number": page_number,
                    "text": "",
                    "blocks": [],
                    "ocr_confidence": 0,
                    "ocr_error": str(e),
                })

                if self._benchmark:
                    self._benchmark.log_page(page_number, 0, 0, "failed")

        doc.close()

        if failed_pages:
            logger.warning(
                f"[DeepSeek OCR2] {len(failed_pages)} page(s) failed OCR: {failed_pages}"
            )

        return {
            "pages": pages_data,
            "tables": all_tables,
            "extraction_method": "ocr",
            "ocr_pages": ocr_pages,
            "failed_pages": failed_pages,
        }

    def _ocr_page_image(
        self, page: fitz.Page, page_number: int
    ) -> Dict:
        """
        OCR satu halaman PDF dengan EasyOCR.
        Render page → convert PIL → numpy → EasyOCR → structured blocks.

        Input validation:
          - PIL.Image.Image → numpy.ndarray (otomatis)
          - grayscale → RGB (otomatis)
          - RGBA → RGB (otomatis)
        """
        reader = self._get_ocr_reader()

        # Render page to numpy array (RGB)
        img_array = self._render_page_to_array(page)
        logger.debug(
            f"[DeepSeek OCR2] Page {page_number} rendered: "
            f"shape={img_array.shape}, dtype={img_array.dtype}"
        )

        # Prepare for OCR: auto-convert if needed
        ocr_input = prepare_image_for_ocr(img_array, f"page {page_number}")

        t0 = time.time()
        results = reader.readtext(
            ocr_input,
            paragraph=True,
            width_ths=0.7,
            height_ths=0.7,
        )
        ocr_time = time.time() - t0

        blocks = []
        full_text_parts = []
        total_confidence = 0.0

        for result in results:
            bbox, text, confidence = normalize_easyocr_result(result)

            if not text or not text.strip():
                continue
            if confidence is not None and confidence < self.config.ocr_confidence_threshold:
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

            block_type = self._classify_block_type_from_ocr(text)
            conf_value = round(float(confidence), 4) if confidence is not None else None

            blocks.append({
                "type": block_type,
                "bbox": bbox_out,
                "content": text.strip(),
                "confidence": conf_value,
            })
            full_text_parts.append(text.strip())
            if confidence is not None:
                total_confidence += float(confidence)

        avg_confidence = (
            total_confidence / len(blocks) if blocks else 0.0
        )

        if self._benchmark:
            self._benchmark.sample_vram()

        return {
            "text": "\n".join(full_text_parts),
            "blocks": blocks,
            "confidence": round(avg_confidence, 4),
            "ocr_time": round(ocr_time, 4),
        }

    def _classify_block_type_from_ocr(self, text: str) -> str:
        text_stripped = text.strip()
        if re.match(r"^#{1,6}\s", text_stripped):
            return "heading"
        if re.match(r"^[-*+]\s", text_stripped) or re.match(r"^\d+[.)]\s", text_stripped):
            return "list"
        if len(text_stripped) > 100:
            return "paragraph"
        return "text"

    # ───────────────────────────────────────────────────────────────── #
    #  Mixed PDF processing                                              #
    # ───────────────────────────────────────────────────────────────── #

    def _process_mixed(self, pdf_path: str) -> Dict:
        logger.info("[DeepSeek OCR2] Processing as mixed PDF...")

        digital_result = self._process_digital(pdf_path)
        doc = fitz.open(pdf_path)

        ocr_pages = []
        failed_pages = []

        for page_data in digital_result["pages"]:
            pn = page_data["page_number"]
            extracted_text = page_data.get("text", "").strip()

            if len(extracted_text) >= self.config.digital_text_min_chars:
                continue

            try:
                page = doc[pn - 1]

                t0 = time.time()
                ocr_result = self._ocr_page_image(page, pn)
                ocr_time = time.time() - t0

                ocr_text = ocr_result.get("text", "").strip()
                ocr_blocks = ocr_result.get("blocks", [])
                ocr_conf = ocr_result.get("confidence", 0)

                if len(ocr_text) > len(extracted_text):
                    page_data["text"] = ocr_text
                    page_data["blocks"] = ocr_blocks
                    page_data["ocr_confidence"] = ocr_conf
                    page_data["ocr_applied"] = True
                else:
                    page_data["ocr_applied"] = False

                ocr_pages.append(pn)
                logger.info(
                    f"[DeepSeek OCR2] Mixed page {pn}: "
                    f"OCR fallback ({len(ocr_text)} chars, {ocr_time:.2f}s, "
                    f"conf={ocr_conf:.3f})"
                )

                if self._benchmark:
                    self._benchmark.log_page(pn, ocr_time, len(ocr_blocks), "ok")

            except Exception as e:
                logger.error(
                    f"[DeepSeek OCR2] Mixed page {pn} OCR failed: {e}"
                )
                failed_pages.append(pn)
                page_data["ocr_applied"] = False
                page_data["ocr_error"] = str(e)

                if self._benchmark:
                    self._benchmark.log_page(pn, 0, 0, "failed")

        doc.close()

        if failed_pages:
            logger.warning(
                f"[DeepSeek OCR2] {len(failed_pages)} mixed page(s) failed OCR: {failed_pages}"
            )

        return {
            "pages": digital_result["pages"],
            "tables": digital_result["tables"],
            "extraction_method": "mixed",
            "ocr_pages": ocr_pages,
            "failed_pages": failed_pages,
        }

    # ───────────────────────────────────────────────────────────────── #
    #  Table extraction                                                  #
    # ───────────────────────────────────────────────────────────────── #

    def _extract_tables_digital(self, pdf_path: str) -> List[Dict]:
        import pdfplumber
        all_tables = []

        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages):
                    page_number = page_num + 1

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

                        cleaned = [
                            [str(cell).strip() if cell is not None else ""
                             for cell in row]
                            for row in table
                        ]

                        max_cols = max((len(r) for r in cleaned), default=0)
                        cleaned = [
                            r + [""] * (max_cols - len(r)) for r in cleaned
                        ]

                        headers = cleaned[0] if cleaned else []
                        rows = cleaned[1:] if len(cleaned) > 1 else []

                        markdown = self._table_to_markdown(cleaned)
                        csv = self._table_to_csv(cleaned)

                        all_tables.append({
                            "page_number": page_number,
                            "table_index": idx,
                            "method": "pdfplumber",
                            "headers": headers,
                            "rows": rows,
                            "markdown": markdown,
                            "csv": csv,
                        })

                        logger.info(
                            f"[DeepSeek OCR2] Table {idx + 1} on page {page_number}: "
                            f"{len(rows)} rows x {max_cols} cols"
                        )

        except Exception as e:
            logger.warning(f"[DeepSeek OCR2] Table extraction error: {e}")

        return all_tables

    def _detect_tables_from_blocks(
        self, blocks: List[Dict], page_number: int
    ) -> List[Dict]:
        tables = []

        text_blocks = [b for b in blocks if b["type"] in ("text", "paragraph")]
        if len(text_blocks) < 4:
            return tables

        table_candidates = self._find_grid_blocks(text_blocks)

        for idx, candidate in enumerate(table_candidates):
            if len(candidate) < 3:
                continue

            rows = []
            for block in candidate:
                cols = re.split(r"\s{2,}|\t", block["content"])
                cols = [c.strip() for c in cols if c.strip()]
                if cols:
                    rows.append(cols)

            if len(rows) < 2:
                continue

            max_cols = max(len(r) for r in rows)
            rows = [r + [""] * (max_cols - len(r)) for r in rows]

            markdown = self._table_to_markdown(rows)
            csv = self._table_to_csv(rows)

            tables.append({
                "page_number": page_number,
                "table_index": idx,
                "method": "ocr-heuristic",
                "headers": rows[0] if rows else [],
                "rows": rows[1:] if len(rows) > 1 else [],
                "markdown": markdown,
                "csv": csv,
            })

        return tables

    def _find_grid_blocks(self, blocks: List[Dict], col_tolerance: float = 30) -> List[List[Dict]]:
        if not blocks:
            return []

        sorted_blocks = sorted(blocks, key=lambda b: (b["bbox"][1], b["bbox"][0]))

        groups = []
        current_group = [sorted_blocks[0]]

        for b in sorted_blocks[1:]:
            last = current_group[-1]
            if abs(b["bbox"][1] - last["bbox"][1]) < col_tolerance:
                current_group.append(b)
            else:
                if len(current_group) >= 3:
                    groups.append(current_group)
                current_group = [b]

        if len(current_group) >= 3:
            groups.append(current_group)

        return groups

    # ───────────────────────────────────────────────────────────────── #
    #  Helpers                                                            #
    # ───────────────────────────────────────────────────────────────── #

    @staticmethod
    def _table_to_markdown(table: List[List[str]]) -> str:
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
    def _table_to_csv(table: List[List[str]]) -> str:
        import csv
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerows(table)
        return output.getvalue()

    # ───────────────────────────────────────────────────────────────── #
    #  Cleanup                                                            #
    # ───────────────────────────────────────────────────────────────── #

    def unload_model(self):
        """Free OCR model from memory."""
        if self._ocr_reader is not None:
            logger.info("[DeepSeek OCR2] Unloading OCR model...")
            del self._ocr_reader
            self._ocr_reader = None
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            logger.info("[DeepSeek OCR2] Model unloaded, GPU memory freed")
