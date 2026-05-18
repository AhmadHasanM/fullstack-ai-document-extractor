from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import uuid
import logging

from ..services.qa_service import QAService
from ..database.db import Database
from ..config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# Lazy initialized instances
_db = None
_qa_service = None


def get_db() -> Database:
    global _db
    if _db is None:
        _db = Database()
    return _db


def get_qa_service() -> QAService:
    global _qa_service
    if _qa_service is None:
        _qa_service = QAService()
    return _qa_service


class ChatRequest(BaseModel):
    document_id: str
    session_id: str
    message: str


class ChatResponse(BaseModel):
    response: str
    session_id: str
    sources: Optional[List[dict]] = None


class CreateSessionRequest(BaseModel):
    document_id: Optional[str] = None
    title: Optional[str] = "New Chat"


class CreateSessionResponse(BaseModel):
    session_id: str
    title: str


class SessionMessage(BaseModel):
    id: str
    role: str
    message: str
    created_at: str


class SessionHistoryResponse(BaseModel):
    session_id: str
    messages: List[SessionMessage]


@router.post("/chat")
async def chat_with_document(request: ChatRequest):
    """Chat with document using RAG"""
    logger.info(f"Chat request - document_id: {request.document_id}, session_id: {request.session_id}")
    try:
        db = get_db()
        qa_service = get_qa_service()

        # Connect to database if not connected
        if not db.pool:
            await db.connect()

        # Get document chunks for RAG
        chunks = []
        if request.document_id:
            try:
                chunks = await db.get_chunks(request.document_id)
                logger.info(f"Found {len(chunks)} chunks for document")
            except Exception as e:
                logger.error(f"Error getting chunks: {e}", exc_info=True)

        # Get response from QA service
        try:
            response_text = await qa_service.answer_question(
                request.document_id or "",
                request.message
            )
            logger.info(f"QA response generated, length: {len(response_text)}")
        except Exception as e:
            logger.error(f"QA service error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"QA service error: {str(e)}")

        # Save chat history
        try:
            await db.save_chat_message(
                document_id=request.document_id,
                session_id=request.session_id,
                role="user",
                message=request.message
            )
        except Exception as e:
            logger.error(f"Error saving user message: {e}", exc_info=True)

        try:
            await db.save_chat_message(
                document_id=request.document_id,
                session_id=request.session_id,
                role="assistant",
                message=response_text
            )
        except Exception as e:
            logger.error(f"Error saving assistant message: {e}", exc_info=True)

        # Extract source references from chunks
        sources = []
        if chunks:
            for chunk in chunks[:3]:
                sources.append({
                    "chunk_index": chunk.get("chunk_index"),
                    "page_number": chunk.get("page_number"),
                    "content_preview": chunk.get("content", "")[:100] + "..."
                })

        return ChatResponse(
            response=response_text,
            session_id=request.session_id,
            sources=sources if sources else None
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in chat: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/sessions")
async def create_chat_session(request: CreateSessionRequest):
    """Create a new chat session"""
    try:
        db = get_db()
        if not db.pool:
            await db.connect()

        session_id = str(uuid.uuid4())
        title = request.title or "New Chat"

        async with db.pool.acquire() as conn:
            query = """
                INSERT INTO chat_sessions (id, document_id, title)
                VALUES ($1, $2, $3)
            """
            await conn.execute(query, session_id, request.document_id, title)

        return CreateSessionResponse(
            session_id=session_id,
            title=title
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chat/sessions")
async def list_chat_sessions():
    """List all chat sessions"""
    try:
        db = get_db()
        if not db.pool:
            await db.connect()

        async with db.pool.acquire() as conn:
            query = """
                SELECT id, document_id, title, created_at, updated_at
                FROM chat_sessions
                ORDER BY updated_at DESC
                LIMIT 50
            """
            rows = await conn.fetch(query)

            sessions = []
            for row in rows:
                sessions.append({
                    "id": row["id"],
                    "document_id": row["document_id"],
                    "title": row["title"],
                    "created_at": row["created_at"].isoformat(),
                    "updated_at": row["updated_at"].isoformat()
                })

            return {"sessions": sessions}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chat/sessions/{session_id}")
async def get_chat_session(session_id: str):
    """Get a specific chat session"""
    try:
        db = get_db()
        if not db.pool:
            await db.connect()

        async with db.pool.acquire() as conn:
            query = """
                SELECT id, document_id, title, created_at, updated_at
                FROM chat_sessions
                WHERE id = $1
            """
            row = await conn.fetchrow(query, session_id)

            if not row:
                raise HTTPException(status_code=404, detail="Session not found")

            return {
                "id": row["id"],
                "document_id": row["document_id"],
                "title": row["title"],
                "created_at": row["created_at"].isoformat(),
                "updated_at": row["updated_at"].isoformat()
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chat/sessions/{session_id}/history")
async def get_session_history(session_id: str):
    """Get chat history for a specific session"""
    try:
        db = get_db()
        if not db.pool:
            await db.connect()

        async with db.pool.acquire() as conn:
            query = """
                SELECT id, document_id, session_id, role, message, created_at
                FROM chat_history
                WHERE session_id = $1
                ORDER BY created_at ASC
                LIMIT 100
            """
            rows = await conn.fetch(query, session_id)

            messages = []
            for row in rows:
                messages.append({
                    "id": str(row["id"]),
                    "role": row["role"],
                    "message": row["message"],
                    "created_at": row["created_at"].isoformat()
                })

            return {
                "session_id": session_id,
                "messages": messages
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/chat/sessions/{session_id}")
async def delete_chat_session(session_id: str):
    """Delete a chat session and its messages"""
    try:
        db = get_db()
        if not db.pool:
            await db.connect()

        async with db.pool.acquire() as conn:
            # Delete messages first (foreign key constraint)
            await conn.execute(
                "DELETE FROM chat_history WHERE session_id = $1",
                session_id
            )
            # Delete session
            await conn.execute(
                "DELETE FROM chat_sessions WHERE id = $1",
                session_id
            )

        return {"message": "Session deleted"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/sessions/{session_id}/messages")
async def send_message_to_session(session_id: str, request: ChatRequest):
    """Send a message to a specific session"""
    logger.info(f"Received message for session: {session_id}")
    try:
        db = get_db()
        qa_service = get_qa_service()

        if not db.pool:
            await db.connect()

        # Get session to find document ID
        async with db.pool.acquire() as conn:
            query = """
                SELECT document_id FROM chat_sessions WHERE id = $1
            """
            row = await conn.fetchrow(query, session_id)

            if not row:
                logger.warning(f"Session not found: {session_id}")
                raise HTTPException(status_code=404, detail="Session not found")

            document_id = row["document_id"]
            logger.info(f"Session document_id: {document_id}")

        # Get response from QA service
        try:
            response_text = await qa_service.answer_question(
                document_id or "",
                request.message
            )
            logger.info(f"QA response generated, length: {len(response_text)}")
        except Exception as e:
            logger.error(f"QA service error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"QA service error: {str(e)}")

        # Save user message
        try:
            await db.save_chat_message(
                document_id=document_id,
                session_id=session_id,
                role="user",
                message=request.message
            )
            logger.info("User message saved")
        except Exception as e:
            logger.error(f"Failed to save user message: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to save user message: {str(e)}")

        # Save assistant message
        try:
            await db.save_chat_message(
                document_id=document_id,
                session_id=session_id,
                role="assistant",
                message=response_text
            )
            logger.info("Assistant message saved")
        except Exception as e:
            logger.error(f"Failed to save assistant message: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to save assistant message: {str(e)}")

        # Update session timestamp
        async with db.pool.acquire() as conn:
            await conn.execute(
                "UPDATE chat_sessions SET updated_at = NOW() WHERE id = $1",
                session_id
            )

        return ChatResponse(
            response=response_text,
            session_id=session_id
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in chat: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/{document_id}/chunks")
async def get_document_chunks(document_id: str):
    """Get document chunks"""
    try:
        db = get_db()
        if not db.pool:
            await db.connect()

        chunks = await db.get_chunks(document_id)
        return {"chunks": chunks}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/documents/{document_id}/regenerate-chunks")
async def regenerate_document_chunks(document_id: str):
    """Regenerate chunks for a document by reading its markdown file"""
    logger.info(f"Regenerating chunks for document: {document_id}")

    try:
        db = get_db()
        if not db.pool:
            await db.connect()

        # Get document to find markdown path
        doc = await db.get_document(document_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        # Get markdown path
        markdown_path = doc.get("markdown_path")
        if not markdown_path:
            # Try default path
            from ..config import settings
            import os
            markdown_path = os.path.join(settings.MARKDOWN_DIR, f"{document_id}.md")

        logger.info(f"Reading markdown from: {markdown_path}")

        # Read markdown file
        if not os.path.exists(markdown_path):
            raise HTTPException(status_code=404, detail=f"Markdown file not found at {markdown_path}")

        with open(markdown_path, "r", encoding="utf-8") as f:
            markdown_content = f.read()

        logger.info(f"Read {len(markdown_content)} chars from markdown")

        # Chunk the document
        from ..services.document_chunker import DocumentChunker
        from ..services.embedding_service import EmbeddingService
        chunker = DocumentChunker(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP
        )
        chunks = chunker.chunk_text(markdown_content, document_id)

        logger.info(f"Created {len(chunks)} chunks")

        # Generate embeddings for each chunk
        logger.info(f"Generating embeddings for {len(chunks)} chunks...")
        embedding_service = EmbeddingService()
        texts = [c.get("content", "") for c in chunks if c.get("content", "").strip()]
        valid_indices = [i for i, c in enumerate(chunks) if c.get("content", "").strip()]

        if texts:
            embeddings = await embedding_service.generate_embeddings_batch(texts)
            if embeddings and len(embeddings) == len(valid_indices):
                for idx, emb in zip(valid_indices, embeddings):
                    chunks[idx]["embedding"] = emb
                logger.info(f"Embeddings attached to {len(embeddings)} chunks")

        # Delete existing chunks for this document
        async with db.pool.acquire() as conn:
            await conn.execute("DELETE FROM document_chunks WHERE document_id = $1", document_id)

        # Save new chunks with embeddings
        await db.save_chunks(chunks)

        chunks_with_emb = sum(1 for c in chunks if c.get("embedding"))
        logger.info(f"Successfully regenerated {len(chunks)} chunks "
                    f"({chunks_with_emb} with embeddings) for document {document_id}")

        return {
            "status": "success",
            "document_id": document_id,
            "chunks_count": len(chunks),
            "chunks_with_embeddings": chunks_with_emb
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error regenerating chunks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug/embeddings")
async def debug_embeddings():
    """Test embedding pipeline without needing a Gemini API key.

    Returns the raw embedding vector dimensions and preview for a known string.
    """
    from ..services.embedding_service import EmbeddingService

    test_text = "This is a test document for embedding verification."
    es = EmbeddingService()
    embedding = await es.generate_embedding(test_text)

    if embedding is None:
        return {
            "status": "error",
            "message": "Embedding generation failed. Check logs for details.",
            "config": {
                "provider": settings.EMBEDDING_PROVIDER,
                "model": settings.EMBEDDING_MODEL,
                "dimension": settings.EMBEDDING_DIMENSION,
                "gemini_api_key_set": bool(settings.GEMINI_API_KEY),
            },
        }

    return {
        "status": "success",
        "dimension": len(embedding),
        "expected_dimension": settings.EMBEDDING_DIMENSION,
        "dimension_match": len(embedding) == settings.EMBEDDING_DIMENSION,
        "first_5_values": embedding[:5],
        "last_5_values": embedding[-5:],
        "config": {
            "provider": settings.EMBEDDING_PROVIDER,
            "model": settings.EMBEDDING_MODEL,
            "dimension": settings.EMBEDDING_DIMENSION,
            "gemini_api_key_set": bool(settings.GEMINI_API_KEY),
        },
    }


@router.post("/documents/reprocess-all")
async def reprocess_all_documents():
    """Reprocess all documents that don't have chunks"""
    logger.info("Starting reprocess-all for documents without chunks")

    try:
        db = get_db()
        if not db.pool:
            await db.connect()

        # Get documents without chunks
        docs = await db.get_documents_without_chunks()
        logger.info(f"Found {len(docs)} documents without chunks")

        results = []
        import os
        from ..services.document_chunker import DocumentChunker
        from ..services.embedding_service import EmbeddingService

        embedding_service = EmbeddingService()

        for doc in docs:
            doc_id = str(doc["id"])
            filename = doc["filename"]

            logger.info(f"Processing document: {doc_id}")

            try:
                # Find markdown file
                from ..config import settings
                markdown_path = os.path.join(settings.MARKDOWN_DIR, f"{doc_id}.md")

                if not os.path.exists(markdown_path):
                    logger.warning(f"Markdown not found for {doc_id}, skipping")
                    results.append({"document_id": doc_id, "status": "skipped", "reason": "markdown_not_found"})
                    continue

                # Read and chunk
                with open(markdown_path, "r", encoding="utf-8") as f:
                    markdown_content = f.read()

                chunker = DocumentChunker(
                    chunk_size=settings.CHUNK_SIZE,
                    chunk_overlap=settings.CHUNK_OVERLAP
                )
                chunks = chunker.chunk_text(markdown_content, doc_id)

                # Generate embeddings
                texts = [c.get("content", "") for c in chunks if c.get("content", "").strip()]
                if texts:
                    embeddings = await embedding_service.generate_embeddings_batch(texts)
                    if embeddings and len(embeddings) == len([i for i, c in enumerate(chunks) if c.get("content", "").strip()]):
                        emb_idx = 0
                        for i, c in enumerate(chunks):
                            if c.get("content", "").strip():
                                chunks[i]["embedding"] = embeddings[emb_idx]
                                emb_idx += 1

                # Save chunks
                await db.save_chunks(chunks)

                chunks_with_emb = sum(1 for c in chunks if c.get("embedding"))
                logger.info(f"Created {len(chunks)} chunks ({chunks_with_emb} with embeddings) for {doc_id}")
                results.append({
                    "document_id": doc_id,
                    "status": "success",
                    "chunks": len(chunks),
                    "chunks_with_embeddings": chunks_with_emb
                })

            except Exception as e:
                logger.error(f"Error processing {doc_id}: {e}")
                results.append({"document_id": doc_id, "status": "error", "reason": str(e)})

        return {
            "status": "completed",
            "processed": len(results),
            "results": results
        }

    except Exception as e:
        logger.error(f"Error in reprocess-all: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))