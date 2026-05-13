import fitz  # PyMuPDF
import pdfplumber
from typing import List, Dict
import re

class TextExtractor:
    """Extract text from PDF files"""
    
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        
    def extract_with_pymupdf(self) -> List[Dict]:
        """Extract text using PyMuPDF (best for digital PDFs)"""
        doc = fitz.open(self.pdf_path)
        pages_data = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            
            # Extract text with layout preservation
            text = page.get_text("text")
            
            # Extract blocks for structure
            blocks = page.get_text("dict")["blocks"]
            
            structured_content = []
            for block in blocks:
                if block["type"] == 0:  # Text block
                    for line in block.get("lines", []):
                        text_content = ""
                        for span in line.get("spans", []):
                            text_content += span.get("text", "")
                        
                        if text_content.strip():
                            structured_content.append({
                                "type": "text",
                                "content": text_content.strip(),
                                "font_size": span.get("size", 12),
                                "font_name": span.get("font", ""),
                                "bbox": line.get("bbox", [])
                            })
            
            pages_data.append({
                "page_number": page_num + 1,
                "raw_text": text,
                "structured_content": structured_content
            })
        
        doc.close()
        return pages_data
    
    def extract_with_pdfplumber(self) -> List[Dict]:
        """Extract text using pdfplumber (good for tables)"""
        pages_data = []
        
        with pdfplumber.open(self.pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                
                pages_data.append({
                    "page_number": page_num + 1,
                    "raw_text": text,
                    "width": page.width,
                    "height": page.height
                })
        
        return pages_data
    
    def detect_headings(self, pages_data: List[Dict]) -> List[Dict]:
        """Detect headings based on font size and formatting"""
        for page in pages_data:
            if "structured_content" not in page:
                continue
                
            # Calculate average font size
            font_sizes = [item["font_size"] for item in page["structured_content"] if "font_size" in item]
            avg_font_size = sum(font_sizes) / len(font_sizes) if font_sizes else 12
            
            # Mark headings
            for item in page["structured_content"]:
                if "font_size" in item and item["font_size"] > avg_font_size * 1.2:
                    item["is_heading"] = True
                    
                    # Determine heading level
                    if item["font_size"] > avg_font_size * 1.8:
                        item["heading_level"] = 1
                    elif item["font_size"] > avg_font_size * 1.5:
                        item["heading_level"] = 2
                    else:
                        item["heading_level"] = 3
        
        return pages_data
    
    def extract_lists(self, text: str) -> List[str]:
        """Extract bullet points and numbered lists"""
        # Pattern for bullet points
        bullet_pattern = r'^[\s]*[•\-\*]\s+(.+)$'
        # Pattern for numbered lists
        number_pattern = r'^[\s]*\d+[\.\)]\s+(.+)$'
        
        lists = []
        for line in text.split('\n'):
            if re.match(bullet_pattern, line) or re.match(number_pattern, line):
                lists.append(line.strip())
        
        return lists