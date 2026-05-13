import os
import json
from typing import Dict, List
from datetime import datetime

from .pdf_detector import PDFDetector
from .text_extractor import TextExtractor
from .table_extractor import TableExtractor
from .image_extractor import ImageExtractor
from .ocr_processor import OCRProcessor
from ..services.markdown_formatter import MarkdownFormatter
from ..config import settings

class PDFProcessor:
    """Main orchestrator for PDF processing"""

    def __init__(self, pdf_path: str, document_id: str):
        self.document_id = document_id

        # ambil nama file saja
        self.pdf_filename = os.path.basename(pdf_path)

        # jika path relatif, arahkan ke uploads dir
        if os.path.isabs(pdf_path):
            self.pdf_path = pdf_path
        else:
            self.pdf_path = os.path.join(
                settings.UPLOADS_DIR,
                self.pdf_filename
            )

        # validasi file ada
        if not os.path.exists(self.pdf_path):
            raise FileNotFoundError(
                f"no such file: '{self.pdf_path}'"
            )

        self.detector = PDFDetector(self.pdf_path)
        self.text_extractor = TextExtractor(self.pdf_path)
        self.table_extractor = TableExtractor()

        # folder output image per dokumen
        self.images_output_dir = os.path.join(
            settings.IMAGES_DIR,
            document_id
        )
        os.makedirs(self.images_output_dir, exist_ok=True)

        self.image_extractor = ImageExtractor(
            self.pdf_path,
            self.images_output_dir
        )

        # ganti ke Surya OCR lokal
        self.ocr_processor = OCRProcessor()

    async def process(self) -> Dict:
        """Process PDF and return results"""
        print(f"📄 Processing PDF: {self.pdf_path}")

        # Step 1: Detect PDF type
        pdf_type = self.detector.detect_type()
        metadata = self.detector.get_metadata()

        print(f"📋 PDF Type: {pdf_type}")
        print(f"📊 Metadata: {metadata.get('page_count', 0)} pages")

        # Step 2: Extract content based on type
        if pdf_type == "digital":
            extraction_result = await self._process_digital_pdf()
        elif pdf_type == "scanned":
            extraction_result = await self._process_scanned_pdf()
        else:
            extraction_result = await self._process_mixed_pdf()

        # Step 3: Extract images
        print("🖼️ Extracting images...")
        images = self.image_extractor.extract_images()
        extraction_result["images"] = images

        # Step 4: Generate structured output
        print("📝 Generating markdown...")
        markdown_content = await self._generate_markdown(
            extraction_result
        )

        # Step 5: Save outputs
        output_paths = await self._save_outputs(
            markdown_content,
            extraction_result,
            metadata
        )

        # Step 6: Chunk document for RAG
        print("✂️ Chunking document...")
        chunks = await self._chunk_document(
            markdown_content
        )

        # Di paling bawah sebelum return

        return {
            "document_id": self.document_id,
            "pdf_type": pdf_type,
            "metadata": metadata,
            "output_paths": output_paths,
            "chunks_count": len(chunks),
            "images_count": len(images),
            "status": "completed"
        }

    async def _process_digital_pdf(self) -> Dict:
        """Process digital PDF (text is extractable)"""
        print("📖 Processing as digital PDF...")

        pages_data = self.text_extractor.extract_with_pymupdf()
        pages_data = self.text_extractor.detect_headings(
            pages_data
        )

        # method baru butuh pdf_path
        tables = self.table_extractor.extract_tables_from_pdf(
            self.pdf_path
        )

        return {
            "pages": pages_data,
            "tables": tables,
            "extraction_method": "digital"
        }

    async def _process_scanned_pdf(self) -> Dict:
        """Process scanned PDF (needs OCR)"""
        print("🔍 Processing as scanned PDF (Surya OCR)...")

        page_images = self.image_extractor.extract_as_png(
            dpi=150
        )

        pages_data = []

        for page_img in page_images:
            ocr_result = self.ocr_processor.process_pdf_page(
                page_img["path"]
            )

            pages_data.append({
                "page_number": page_img["page_number"],
                "raw_text": ocr_result.get("text", ""),
                "ocr_confidence": ocr_result.get(
                    "confidence",
                    "unknown"
                ),
                "image_path": page_img["path"]
            })

        # Extract tables from images
        tables = []

        for page_img in page_images:
            page_tables = (
                self.ocr_processor
                .extract_tables_from_image(
                    page_img["path"]
                )
            )
            tables.extend(page_tables)

        return {
            "pages": pages_data,
            "tables": tables,
            "extraction_method": "ocr"
        }

    async def _process_mixed_pdf(self) -> Dict:
        """Process mixed PDF"""
        print("🔀 Processing as mixed PDF...")

        digital_result = await self._process_digital_pdf()

        pages_needing_ocr = []

        for page in digital_result["pages"]:
            raw_text = page.get(
                "raw_text",
                ""
            ).strip()

            if len(raw_text) < 100:
                pages_needing_ocr.append(
                    page["page_number"]
                )

        if pages_needing_ocr:
            print(
                f"🔍 Running Surya OCR on "
                f"{len(pages_needing_ocr)} pages..."
            )

            page_images = (
                self.image_extractor.extract_as_png(
                    dpi=300
                )
            )

            for page_img in page_images:
                if (
                    page_img["page_number"]
                    in pages_needing_ocr
                ):
                    ocr_result = (
                        self.ocr_processor
                        .process_pdf_page(
                            page_img["path"]
                        )
                    )

                    for page in digital_result["pages"]:
                        if (
                            page["page_number"]
                            == page_img["page_number"]
                        ):
                            ocr_text = ocr_result.get(
                                "text",
                                ""
                            ).strip()

                            if len(ocr_text) > len(
                                page["raw_text"]
                            ):
                                page["raw_text"] = ocr_text

                            page["ocr_applied"] = True
                            break

        return {
            "pages": digital_result["pages"],
            "tables": digital_result["tables"],
            "extraction_method": "mixed",
            "ocr_pages": pages_needing_ocr
        }

    async def _generate_markdown(
        self,
        extraction_result: Dict
    ) -> str:
        """Generate markdown"""
        formatter = MarkdownFormatter(
            settings.GEMINI_API_KEY
        )

        markdown = await formatter.format(
            extraction_result
        )

        return markdown

    async def _save_outputs(
        self,
        markdown: str,
        extraction_result: Dict,
        metadata: Dict
    ) -> Dict:
        """Save outputs"""

        os.makedirs(
            settings.MARKDOWN_DIR,
            exist_ok=True
        )

        os.makedirs(
            settings.JSON_DIR,
            exist_ok=True
        )

        markdown_path = os.path.join(
            settings.MARKDOWN_DIR,
            f"{self.document_id}.md"
        )

        with open(
            markdown_path,
            "w",
            encoding="utf-8"
        ) as f:
            f.write(markdown)

        json_data = {
            "document_id": self.document_id,
            "filename": self.pdf_filename,
            "metadata": metadata,
            "extraction_result": extraction_result,
            "processed_at": datetime.now().isoformat()
        }

        json_path = os.path.join(
            settings.JSON_DIR,
            f"{self.document_id}.json"
        )

        with open(
            json_path,
            "w",
            encoding="utf-8"
        ) as f:
            json.dump(
                json_data,
                f,
                indent=2,
                ensure_ascii=False
            )

        return {
            "markdown_path": markdown_path,
            "json_path": json_path,
            "images_folder": self.images_output_dir
        }

    async def _chunk_document(
        self,
        markdown: str
    ) -> List[Dict]:
        """Chunk document for vector storage"""

        from ..services.document_chunker import (
            DocumentChunker
        )

        if not markdown.strip():
            return []

        chunker = DocumentChunker(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP
        )

        chunks = chunker.chunk_text(
            markdown,
            self.document_id
        )

        return chunks