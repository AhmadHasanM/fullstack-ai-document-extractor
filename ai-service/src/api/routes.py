from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import Optional
import os

from ..extractors.pdf_processor import PDFProcessor
from ..database.db import Database
from ..config import settings

router = APIRouter()
db = Database()

class ChatRequest(BaseModel):
    document_id: str
    session_id: str
    message: str

class ChatResponse(BaseModel):
    response: str
    session_id: str

@router.post("/process")
async def process_pdf(document_id: str, pdf_path: str):
    """Manually trigger PDF processing"""
    try:
        processor = PDFProcessor(pdf_path, document_id)
        result = await processor.process()
        return {"status": "success", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/chat")
async def chat_with_document(request: ChatRequest):
    """Chat with document using RAG"""
    try:
        # Get document chunks
        chunks = await db.get_chunks(request.document_id)
        
        if not chunks:
            raise HTTPException(status_code=404, detail="Document not found or not processed")
        
        # TODO: Implement RAG-based Q&A
        # 1. Embed the question
        # 2. Find similar chunks
        # 3. Generate response using Gemini with context
        
        response = f"Mock response for: {request.message}"
        
        # Save chat history
        await db.save_chat_message(
            document_id=request.document_id,
            session_id=request.session_id,
            role="user",
            message=request.message
        )
        
        await db.save_chat_message(
            document_id=request.document_id,
            session_id=request.session_id,
            role="assistant",
            message=response
        )
        
        return ChatResponse(response=response, session_id=request.session_id)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/documents/{document_id}/chunks")
async def get_document_chunks(document_id: str):
    """Get document chunks"""
    try:
        chunks = await db.get_chunks(document_id)
        return {"chunks": chunks}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))