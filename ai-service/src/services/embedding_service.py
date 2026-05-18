import asyncio
import logging
import time
from typing import List, Optional

import google.generativeai as genai

from ..config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Generate embeddings using Gemini API with sentence-transformers fallback.

    Primary: google.generativeai embed_content (models/text-embedding-004, 768d)
    Fallback: sentence-transformers all-mpnet-base-v2 (768d)
    """

    def __init__(self):
        self._transformer_model = None
        self._initialized = True
        self._provider = settings.EMBEDDING_PROVIDER
        self._model_name = settings.EMBEDDING_MODEL

    # ----------------------------------------------------------------
    # Primary: Gemini embedding via google.generativeai
    # ----------------------------------------------------------------

    def _gemini_embed(self, texts: List[str]) -> Optional[List[List[float]]]:
        if not settings.GEMINI_API_KEY:
            logger.warning("GEMINI_API_KEY not set, cannot use Gemini embedding")
            return None

        try:
            genai.configure(api_key=settings.GEMINI_API_KEY)

            embeddings = []
            for text in texts:
                result = genai.embed_content(
                    model=self._model_name,
                    content=text,
                )
                emb = list(result.embedding.values)

                if len(emb) != settings.EMBEDDING_DIMENSION:
                    logger.warning(
                        f"Embedding dimension mismatch: got {len(emb)}, "
                        f"expected {settings.EMBEDDING_DIMENSION}"
                    )

                embeddings.append(emb)

            logger.info(
                f"Gemini embedding generated for {len(texts)} texts, "
                f"dim={len(embeddings[0]) if embeddings else 0}, "
                f"first_3_values={embeddings[0][:3] if embeddings else 'N/A'}"
            )
            return embeddings

        except Exception as e:
            logger.error(f"Gemini embedding failed: {e}", exc_info=True)
            return None

    # ----------------------------------------------------------------
    # Fallback: sentence-transformers
    # ----------------------------------------------------------------

    def _get_transformer_model(self):
        if self._transformer_model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._transformer_model = SentenceTransformer("all-mpnet-base-v2")
                logger.info("sentence-transformers model loaded: all-mpnet-base-v2")
            except Exception as e:
                logger.error(f"Failed to load sentence-transformers: {e}", exc_info=True)
                raise
        return self._transformer_model

    def _transformer_embed(self, texts: List[str]) -> Optional[List[List[float]]]:
        try:
            model = self._get_transformer_model()
            embeddings = model.encode(texts, show_progress_bar=False).tolist()
            logger.info(
                f"sentence-transformers embedding for {len(texts)} texts, "
                f"dim={len(embeddings[0]) if embeddings else 0}, "
                f"first_3_values={embeddings[0][:3] if embeddings else 'N/A'}"
            )
            return embeddings
        except Exception as e:
            logger.error(f"sentence-transformers embedding failed: {e}", exc_info=True)
            return None

    # ----------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------

    async def generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding for a single text string."""
        results = await self.generate_embeddings_batch([text])
        if results:
            return results[0]
        return None

    async def generate_embeddings_batch(
        self, texts: List[str]
    ) -> Optional[List[List[float]]]:
        """Generate embeddings for a batch of texts.

        Tries Gemini first, falls back to sentence-transformers.
        Returns None if both fail.
        """
        if not texts:
            return []

        start = time.time()
        logger.info(f"Embedding generation started for {len(texts)} texts")

        embeddings = None
        provider_used = None

        if self._provider == "gemini" or self._provider == "auto":
            embeddings = await asyncio.to_thread(self._gemini_embed, texts)
            if embeddings is not None:
                provider_used = "gemini"

        if embeddings is None and (self._provider == "sentence-transformers" or self._provider == "auto"):
            logger.info("Falling back to sentence-transformers")
            embeddings = await asyncio.to_thread(self._transformer_embed, texts)
            if embeddings is not None:
                provider_used = "sentence-transformers"

        elapsed = time.time() - start

        if embeddings is not None:
            logger.info(
                f"Embedding generation completed: {len(texts)} texts in {elapsed:.2f}s, "
                f"provider={provider_used}"
            )
            return embeddings

        logger.error(f"Embedding generation failed for all providers ({elapsed:.2f}s)")
        return None

    async def generate_query_embedding(self, query: str) -> Optional[List[float]]:
        """Generate embedding for a search query.

        Uses the same model as document embeddings for consistent comparison.
        """
        result = await self.generate_embeddings_batch([query])
        if result:
            logger.info(f"Query embedding generated, dim={len(result[0])}")
            return result[0]
        logger.warning("Query embedding generation failed")
        return None
