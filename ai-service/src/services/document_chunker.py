from typing import List, Dict
import re

class DocumentChunker:
    """Chunk documents for vector storage and RAG"""
    
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
    
    def chunk_text(self, text: str, document_id: str) -> List[Dict]:
        """Chunk text into overlapping segments"""
        chunks = []
        
        # Split by paragraphs first
        paragraphs = text.split('\n\n')
        
        current_chunk = ""
        chunk_index = 0
        
        for para in paragraphs:
            # If adding this paragraph exceeds chunk size
            if len(current_chunk) + len(para) > self.chunk_size:
                # Save current chunk
                if current_chunk:
                    chunks.append({
                        "document_id": document_id,
                        "chunk_index": chunk_index,
                        "content": current_chunk.strip(),
                        "char_count": len(current_chunk),
                        "chunk_type": "text"
                    })
                    chunk_index += 1
                
                # Start new chunk with overlap
                if self.chunk_overlap > 0 and current_chunk:
                    overlap_text = current_chunk[-self.chunk_overlap:]
                    current_chunk = overlap_text + "\n\n" + para
                else:
                    current_chunk = para
            else:
                current_chunk += "\n\n" + para if current_chunk else para
        
        # Add last chunk
        if current_chunk:
            chunks.append({
                "document_id": document_id,
                "chunk_index": chunk_index,
                "content": current_chunk.strip(),
                "char_count": len(current_chunk),
                "chunk_type": "text"
            })
        
        return chunks
    
    def chunk_by_sections(self, markdown: str, document_id: str) -> List[Dict]:
        """Chunk by markdown sections (headings)"""
        chunks = []
        
        # Split by headings
        sections = re.split(r'\n(#{1,6}\s+.+)\n', markdown)
        
        current_section = ""
        current_heading = None
        chunk_index = 0
        
        for i, section in enumerate(sections):
            # Check if this is a heading
            if re.match(r'^#{1,6}\s+', section):
                # Save previous section
                if current_section:
                    chunks.append({
                        "document_id": document_id,
                        "chunk_index": chunk_index,
                        "content": current_section.strip(),
                        "heading": current_heading,
                        "chunk_type": "section"
                    })
                    chunk_index += 1
                
                current_heading = section
                current_section = section + "\n"
            else:
                current_section += section
        
        # Add last section
        if current_section:
            chunks.append({
                "document_id": document_id,
                "chunk_index": chunk_index,
                "content": current_section.strip(),
                "heading": current_heading,
                "chunk_type": "section"
            })
        
        return chunks
    
    def extract_metadata(self, chunk: str) -> Dict:
        """Extract metadata from chunk"""
        metadata = {
            "has_table": "| --- |" in chunk or "|---|" in chunk,
            "has_list": bool(re.search(r'^\s*[-\*\d+\.]\s', chunk, re.MULTILINE)),
            "has_code": "```" in chunk,
            "has_formula": "$" in chunk or "\\(" in chunk,
            "word_count": len(chunk.split()),
        }
        return metadata