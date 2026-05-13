import fitz  # PyMuPDF
import pdfplumber
from typing import Literal

class PDFDetector:
    """Detects PDF type: digital, scanned, or mixed"""
    
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        
    def detect_type(self) -> Literal["digital", "scanned", "mixed"]:
        """
        Detect if PDF is digital, scanned, or mixed
        
        Returns:
            "digital": PDF with extractable text
            "scanned": PDF with images only (needs OCR)
            "mixed": PDF with both text and images
        """
        doc = fitz.open(self.pdf_path)
        
        total_pages = len(doc)
        pages_with_text = 0
        pages_with_images = 0
        
        for page_num in range(total_pages):
            page = doc[page_num]
            
            # Check for text
            text = page.get_text().strip()
            if text and len(text) > 50:  # Minimal text threshold
                pages_with_text += 1
            
            # Check for images
            image_list = page.get_images()
            if image_list:
                pages_with_images += 1
        
        doc.close()
        
        # Calculate percentages
        text_percentage = (pages_with_text / total_pages) * 100
        image_percentage = (pages_with_images / total_pages) * 100
        
        # Decision logic
        if text_percentage > 80:
            return "digital"
        elif text_percentage < 20 and image_percentage > 50:
            return "scanned"
        else:
            return "mixed"
    
    def get_metadata(self) -> dict:
        """Get PDF metadata"""
        doc = fitz.open(self.pdf_path)
        metadata = doc.metadata
        
        info = {
            "title": metadata.get("title", ""),
            "author": metadata.get("author", ""),
            "subject": metadata.get("subject", ""),
            "creator": metadata.get("creator", ""),
            "producer": metadata.get("producer", ""),
            "creation_date": metadata.get("creationDate", ""),
            "mod_date": metadata.get("modDate", ""),
            "page_count": len(doc)
        }
        
        doc.close()
        return info