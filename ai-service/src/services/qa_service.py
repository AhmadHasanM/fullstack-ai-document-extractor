import google.generativeai as genai
import logging
import re
import time
from ..database.db import Database
from ..config import settings
from ..services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 4000

INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous\s+)?instructions",
    r"ignore\s+(all\s+)?(previous\s+)?(prompts|context)",
    r"forget\s+(all\s+)?(previous\s+)?(instructions|prompts|context)",
    r"disregard\s+(all\s+)?(previous\s+)?(instructions|prompts|context)",
    r"you\s+are\s+(now|not\s+bound)",
    r"system\s+prompt",
    r"\[system\]",
    r"<\|im_start\|>",
    r"<\|im_end\|>",
    r"<\s*[sS][yY][sS][tT][eE][mM]\s*>",
]


class QAService:
    """Question Answering Service with vector similarity retrieval."""

    def __init__(self):
        self.db = Database()
        self.embedding_service = EmbeddingService()

        if settings.GEMINI_API_KEY:
            try:
                genai.configure(api_key=settings.GEMINI_API_KEY)
                self.model = genai.GenerativeModel("gemini-2.5-flash")
                logger.info("Gemini model initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini model: {e}")
                self.model = None
        else:
            logger.warning("GEMINI_API_KEY not configured")
            self.model = None

    def _sanitize_input(self, text: str) -> str:
        if not text:
            return ""

        if len(text) > MAX_MESSAGE_LENGTH:
            text = text[:MAX_MESSAGE_LENGTH]

        text = re.sub(r"<\|im_start\|>", "", text)
        text = re.sub(r"<\|im_end\|>", "", text)
        text = re.sub(r"<\s*[sS][yY][sS][tT][eE][mM]\s*>", "", text)

        return text

    def _has_injection_attempt(self, text: str) -> bool:
        text_lower = text.lower()
        for pattern in INJECTION_PATTERNS:
            if re.search(pattern, text_lower):
                logger.warning(f"Potential injection attempt detected: {pattern}")
                return True
        return False

    async def _retrieve_relevant_chunks(
        self, document_id: str, question: str
    ) -> list:
        """Retrieve relevant chunks using vector similarity search.

        Generates query embedding, searches pgvector, returns chunks.
        Falls back to sequential retrieval if vector search fails or
        embeddings don't exist.
        """
        top_k = settings.TOP_K_RESULTS
        min_similarity = settings.MIN_SIMILARITY
        max_chars = settings.MAX_CONTEXT_CHARS

        # Try vector search first
        query_embedding = await self.embedding_service.generate_query_embedding(
            question
        )

        if query_embedding:
            logger.info(
                f"Vector search: query_embedding generated (dim={len(query_embedding)})"
            )
            results = await self.db.search_similar_chunks(
                document_id=document_id,
                query_embedding=query_embedding,
                top_k=top_k,
                min_similarity=min_similarity,
            )

            if results:
                logger.info(
                    f"Vector search returned {len(results)} relevant chunks"
                )
                for r in results:
                    logger.info(
                        f"  chunk {r.get('chunk_index')}: "
                        f"similarity={r.get('similarity', 0):.4f}"
                    )
                return self._build_context(results, max_chars)

        # If no embeddings exist or vector search fails, fallback to sequential
        logger.info("Vector search unavailable, falling back to sequential retrieval")
        chunks = await self.db.get_chunks(document_id)

        if not chunks:
            logger.warning(f"No chunks found for document {document_id}")
            return ""

        logger.info(f"Sequential fallback: using first {min(top_k, len(chunks))} chunks")
        return self._build_context(chunks[:top_k], max_chars)

    def _build_context(self, chunks: list, max_chars: int) -> str:
        """Build context string from chunks within character limit."""
        parts = []
        total = 0

        for chunk in chunks:
            content = chunk.get("content", "")
            similarity = chunk.get("similarity")

            if similarity is not None:
                prefix = f"[Relevance: {similarity:.2%}]\n"
            else:
                prefix = ""

            text = prefix + content

            if total + len(text) > max_chars:
                remaining = max_chars - total
                if remaining > 200:
                    parts.append(text[:remaining])
                break

            parts.append(text)
            total += len(text)

        return "\n\n---\n\n".join(parts)

    async def answer_question(self, document_id: str, question: str) -> str:
        logger.info(f"Processing question for document_id: {document_id}")
        start = time.time()

        safe_question = self._sanitize_input(question)

        if self._has_injection_attempt(safe_question):
            logger.warning(f"Injection attempt blocked for document: {document_id}")
            return "I can only answer questions about the document content. Please ask a document-related question."

        if not document_id:
            logger.warning("No document_id provided, using general knowledge mode")
            return await self._answer_without_document(safe_question)

        if not self.db.pool:
            logger.info("Connecting to database...")
            await self.db.connect()

        # Retrieve relevant context using vector search
        context = await self._retrieve_relevant_chunks(document_id, safe_question)

        if not context:
            logger.warning(f"No relevant content found for document {document_id}")
            return "No document content available. Please upload and process a document first."

        if not self.model:
            logger.error("Gemini model not available")
            return "AI model not configured. Please set GEMINI_API_KEY."

        try:
            prompt = f"""You are a helpful AI assistant for document analysis.

Answer the question based ONLY on the provided document context.

DOCUMENT CONTEXT:
{context}

QUESTION:
{safe_question}

ANSWER:
"""
            logger.info("Calling Gemini API...")
            response = self.model.generate_content(prompt)
            elapsed = time.time() - start
            logger.info(f"Got response from Gemini in {elapsed:.2f}s")
            return response.text
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            elapsed = time.time() - start
            return f"Error generating response. Please try again."

    async def _answer_without_document(self, question: str) -> str:
        """Answer general questions without document context"""
        if not self.model:
            return "AI model not configured. Please set GEMINI_API_KEY."

        try:
            prompt = f"""You are a helpful AI assistant specializing in document analysis.

If the user asks a general question, provide a helpful answer. If it seems related to document analysis or extraction, explain that you need a document to provide specific information.

Question: {question}
"""
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            logger.error(f"Error in general Q&A: {e}")
            return "Error processing question. Please try again."
