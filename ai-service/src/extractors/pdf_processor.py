import os
import json
from typing import Dict, List
from datetime import datetime

from .pdf_detector import PDFDetector
from .text_extractor import TextExtractor
from .table_extractor import TableExtractor
from .image_extractor import ImageExtractor
from .ocr_processor import OCRProcessor
from ..services.deepseek_ocr_service import DeepSeekOCRService, DeepSeekOCRConfig
from ..services.markdown_formatter import MarkdownFormatter
from ..services.embedding_service import EmbeddingService
from ..database.db import Database
from ..config import settings


class PDFProcessor:
    """Main orchestrator for PDF processing — uses DeepSeek OCR2"""

    def __init__(self, pdf_path: str, document_id: str):
        self.document_id = document_id
        self.pdf_filename = os.path.basename(pdf_path)

        if os.path.isabs(pdf_path):
            self.pdf_path = pdf_path
        else:
            self.pdf_path = os.path.join(settings.UPLOADS_DIR, self.pdf_filename)

        if not os.path.exists(self.pdf_path):
            raise FileNotFoundError(f"no such file: '{self.pdf_path}'")

        self.detector = PDFDetector(self.pdf_path)
        self.text_extractor = TextExtractor(self.pdf_path)

        # DeepSeek OCR2 — local inference engine (GPU-first)
        ocr_config = DeepSeekOCRConfig(
            device="cuda" if __import__("torch").cuda.is_available() else "cpu",
            use_gpu=__import__("torch").cuda.is_available(),
        )
        self.deepseek_ocr = DeepSeekOCRService(ocr_config)

        # Table extractor — local, no transformers, uses pdfplumber + OCR blocks
        self.table_extractor = TableExtractor()

        self.images_output_dir = os.path.join(settings.IMAGES_DIR, document_id)
        os.makedirs(self.images_output_dir, exist_ok=True)

        self.image_extractor = ImageExtractor(self.pdf_path, self.images_output_dir)
        self.ocr_processor = OCRProcessor()
        self.embedding_service = EmbeddingService()

    async def process(self) -> Dict:
        """Process PDF using DeepSeek OCR2 engine"""
        print(f"[DeepSeek OCR2] Processing: {self.pdf_path}")

        pdf_type = self.detector.detect_type()
        metadata = self.detector.get_metadata()
        print(f"[DeepSeek OCR2] Type: {pdf_type}, Pages: {metadata.get('page_count', 0)}")

        # Step 1-2: DeepSeek OCR2 full pipeline
        extraction_result = self.deepseek_ocr.process_document(self.pdf_path)

        # Step 3: Extract embedded images
        print("[DeepSeek OCR2] Extracting images...")
        images = self.image_extractor.extract_images()
        extraction_result["images"] = images

        # Step 4: Generate markdown
        print("[DeepSeek OCR2] Generating markdown...")
        markdown_content = await self._generate_markdown(extraction_result)

        # Step 5: Save outputs
        output_paths = await self._save_outputs(markdown_content, extraction_result, metadata)

        # Step 6: Chunk document
        print("[DeepSeek OCR2] Chunking document...")
        chunks = await self._chunk_document(markdown_content)

        # Step 7: Generate embeddings
        if chunks:
            print(f"[DeepSeek OCR2] Generating embeddings for {len(chunks)} chunks...")
            await self._generate_chunk_embeddings(chunks)

            print(f"[DeepSeek OCR2] Saving {len(chunks)} chunks to database...")
            db = Database()
            await db.connect()
            await db.save_chunks(chunks)
            print("[DeepSeek OCR2] Chunks saved successfully")
        else:
            print("[DeepSeek OCR2] No chunks to save")

        chunks_with_embeddings = sum(1 for c in chunks if c.get("embedding"))
        print(f"[DeepSeek OCR2] Chunks with embeddings: {chunks_with_embeddings}/{len(chunks) or 0}")

        return {
            "document_id": self.document_id,
            "pdf_type": pdf_type,
            "metadata": metadata,
            "output_paths": output_paths,
            "chunks_count": len(chunks),
            "chunks_with_embeddings": chunks_with_embeddings,
            "images_count": len(images),
            "status": "completed",
        }

    async def _generate_markdown(self, extraction_result: Dict) -> str:
        formatter = MarkdownFormatter(settings.GEMINI_API_KEY)
        return await formatter.format(extraction_result)

    async def _save_outputs(self, markdown: str, extraction_result: Dict, metadata: Dict) -> Dict:
        os.makedirs(settings.MARKDOWN_DIR, exist_ok=True)
        os.makedirs(settings.JSON_DIR, exist_ok=True)

        markdown_path = os.path.join(settings.MARKDOWN_DIR, f"{self.document_id}.md")
        with open(markdown_path, "w", encoding="utf-8") as f:
            f.write(markdown)

        json_data = {
            "document_id": self.document_id,
            "filename": self.pdf_filename,
            "metadata": metadata,
            "extraction_result": extraction_result,
            "processed_at": datetime.now().isoformat(),
        }

        json_path = os.path.join(settings.JSON_DIR, f"{self.document_id}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)

        return {
            "markdown_path": markdown_path,
            "json_path": json_path,
            "images_folder": self.images_output_dir,
        }

    async def _chunk_document(self, markdown: str) -> List[Dict]:
        from ..services.document_chunker import DocumentChunker

        if not markdown.strip():
            return []

        chunker = DocumentChunker(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
        )
        return chunker.chunk_text(markdown, self.document_id)

    async def _generate_chunk_embeddings(self, chunks: List[Dict]) -> None:
        texts = [c.get("content", "") for c in chunks]
        if not texts:
            return

        valid_indices = [i for i, t in enumerate(texts) if t.strip()]
        valid_texts = [texts[i] for i in valid_indices]

        if not valid_texts:
            print("[DeepSeek OCR2] No chunk content to embed")
            return

        print(f"[DeepSeek OCR2] Generating embeddings for {len(valid_texts)} chunks...")
        embeddings = await self.embedding_service.generate_embeddings_batch(valid_texts)

        if embeddings is not None and len(embeddings) == len(valid_indices):
            for idx, emb in zip(valid_indices, embeddings):
                chunks[idx]["embedding"] = emb
            print(f"[DeepSeek OCR2] Embeddings attached to {len(embeddings)} chunks")
        else:
            print(f"[DeepSeek OCR2] Embedding generation returned no results")
