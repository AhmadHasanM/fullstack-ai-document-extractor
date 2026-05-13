import fitz  # PyMuPDF
from PIL import Image
import io
import os
from typing import List, Dict

class ImageExtractor:
    """Extract images from PDF files"""
    
    def __init__(self, pdf_path: str, output_dir: str):
        self.pdf_path = pdf_path
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        
    def extract_images(self) -> List[Dict]:
        """Extract all images from PDF"""
        doc = fitz.open(self.pdf_path)
        images_data = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            image_list = page.get_images()
            
            for img_idx, img in enumerate(image_list):
                xref = img[0]
                
                try:
                    # Extract image
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    image_ext = base_image["ext"]
                    
                    # Generate filename
                    image_filename = f"page_{page_num + 1}_img_{img_idx + 1}.{image_ext}"
                    image_path = os.path.join(self.output_dir, image_filename)
                    
                    # Save image
                    with open(image_path, "wb") as img_file:
                        img_file.write(image_bytes)
                    
                    # Get image dimensions
                    pil_image = Image.open(io.BytesIO(image_bytes))
                    width, height = pil_image.size
                    
                    images_data.append({
                        "page_number": page_num + 1,
                        "image_index": img_idx + 1,
                        "filename": image_filename,
                        "path": image_path,
                        "format": image_ext,
                        "width": width,
                        "height": height,
                        "size_bytes": len(image_bytes)
                    })
                    
                except Exception as e:
                    print(f"Error extracting image {img_idx} from page {page_num + 1}: {str(e)}")
                    continue
        
        doc.close()
        return images_data
    
    def extract_as_png(self, dpi: int = 300) -> List[Dict]:
        """Convert PDF pages to PNG images (useful for scanned PDFs)"""
        doc = fitz.open(self.pdf_path)
        page_images = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            
            # Render page to image
            mat = fitz.Matrix(dpi / 72, dpi / 72)  # Scale factor for DPI
            pix = page.get_pixmap(matrix=mat)
            
            # Generate filename
            image_filename = f"page_{page_num + 1}_full.png"
            image_path = os.path.join(self.output_dir, image_filename)
            
            # Save as PNG
            pix.save(image_path)
            
            page_images.append({
                "page_number": page_num + 1,
                "filename": image_filename,
                "path": image_path,
                "format": "png",
                "width": pix.width,
                "height": pix.height,
                "dpi": dpi
            })
        
        doc.close()
        return page_images
    
    def get_image_bbox(self, page, xref: int) -> tuple:
        """Get bounding box of an image on a page"""
        image_list = page.get_images()
        
        for img in image_list:
            if img[0] == xref:
                # Get image rectangle
                image_rects = page.get_image_rects(xref)
                if image_rects:
                    rect = image_rects[0]
                    return (rect.x0, rect.y0, rect.x1, rect.y1)
        
        return None