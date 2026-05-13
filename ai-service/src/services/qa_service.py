import google.generativeai as genai
from ..database.db import Database
from ..config import settings


class QAService:
    """Question Answering Service using document chunks"""

    def __init__(self):
        self.db = Database()

        if settings.GEMINI_API_KEY:
            genai.configure(api_key=settings.GEMINI_API_KEY)
            self.model = genai.GenerativeModel("gemini-2.5-flash")
        else:
            self.model = None

    async def answer_question(self, document_id: str, question: str) -> str:
        chunks = await self.db.get_chunks(document_id)

        if not chunks:
            return "No document chunks found."

        context = "\n\n".join([
            chunk["content"]
            for chunk in chunks[:10]
        ])

        if not self.model:
            return "Gemini API key is not configured."

        prompt = f"""
You are a helpful AI assistant.

Answer the question based ONLY on the provided document context.

DOCUMENT CONTEXT:
{context}

QUESTION:
{question}

ANSWER:
"""

        response = self.model.generate_content(prompt)

        return response.text