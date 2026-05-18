import google.generativeai as genai
import logging
from ..database.db import Database
from ..config import settings

logger = logging.getLogger(__name__)


class QAService:
    """Question Answering Service using document chunks"""

    def __init__(self):
        self.db = Database()

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

    async def answer_question(self, document_id: str, question: str) -> str:
        logger.info(f"Processing question for document_id: {document_id}")
        logger.info(f"Question: {question[:100]}...")

        # Handle empty or invalid document_id
        if not document_id:
            logger.warning("No document_id provided, using general knowledge mode")
            return await self._answer_without_document(question)

        # Ensure database is connected
        if not self.db.pool:
            logger.info("Connecting to database...")
            await self.db.connect()

        try:
            chunks = await self.db.get_chunks(document_id)
            logger.info(f"Retrieved {len(chunks)} chunks from database for document_id: {document_id}")

            if chunks:
                # Log first chunk preview for debugging
                logger.info(f"First chunk preview: {chunks[0].get('content', '')[:200]}...")

        except Exception as e:
            logger.error(f"Failed to get chunks for document {document_id}: {e}", exc_info=True)
            return f"Error retrieving document chunks: {str(e)}"

        if not chunks:
            logger.warning(f"No chunks found for document {document_id}")
            # Let's check if the document exists in the database
            try:
                doc = await self.db.get_document(document_id)
                if doc:
                    logger.info(f"Document exists: {doc.get('filename', 'unknown')}")
                    logger.info(f"Document status: {doc.get('status', 'unknown')}")
                else:
                    logger.warning("Document not found in database")
            except Exception as e:
                logger.error(f"Error checking document: {e}")
            return "No document content available. Please upload and process a document first."

        logger.info(f"Found {len(chunks)} chunks, using top 10")

        context = "\n\n".join([
            chunk["content"]
            for chunk in chunks[:10]
        ])

        if not self.model:
            logger.error("Gemini model not available")
            return "AI model not configured. Please set GEMINI_API_KEY."

        try:
            prompt = f"""
You are a helpful AI assistant.

Answer the question based ONLY on the provided document context.

DOCUMENT CONTEXT:
{context}

QUESTION:
{question}

ANSWER:
"""
            logger.info("Calling Gemini API...")
            response = self.model.generate_content(prompt)
            logger.info("Got response from Gemini")
            return response.text
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return f"Error generating response: {str(e)}"

    async def _answer_without_document(self, question: str) -> str:
        """Answer general questions without document context"""
        if not self.model:
            return "AI model not configured. Please set GEMINI_API_KEY."

        try:
            prompt = f"""
You are a helpful AI assistant specializing in document analysis.

Question: {question}

If this is a general question, provide a helpful answer. If it seems related to document analysis or extraction, explain that you need a document to provide specific information.
"""
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            logger.error(f"Error in general Q&A: {e}")
            return f"Error processing question: {str(e)}"