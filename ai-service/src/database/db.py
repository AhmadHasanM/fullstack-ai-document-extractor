import asyncpg
from typing import Optional, Dict, List, Any
from datetime import datetime
from ..config import settings


def convert_embedding_to_pgvector(vector: List[float]) -> str:
    """Convert a Python list of floats to pgvector string format.

    asyncpg requires pgvector values as strings like '[0.1,0.2,0.3]'.
    """
    return "[" + ",".join(str(v) for v in vector) + "]"


class Database:
    """Database operations helper"""

    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        """Create database connection pool and ensure tables exist"""
        if not self.pool:
            self.pool = await asyncpg.create_pool(
                settings.DATABASE_URL,
                min_size=2,
                max_size=10
            )
            await self._ensure_tables()

    async def _ensure_tables(self):
        """Create tables if they don't exist and add missing columns + indexes"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    document_id UUID REFERENCES documents(id) ON DELETE SET NULL,
                    title VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
                    session_id UUID REFERENCES chat_sessions(id) ON DELETE CASCADE,
                    role VARCHAR(20) CHECK (role IN ('user', 'assistant')),
                    message TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await self._add_column_if_not_exists(conn, "documents", "user_id",
                "ALTER TABLE documents ADD COLUMN user_id UUID REFERENCES users(id) ON DELETE CASCADE")
            await self._add_column_if_not_exists(conn, "chat_sessions", "user_id",
                "ALTER TABLE chat_sessions ADD COLUMN user_id UUID REFERENCES users(id) ON DELETE CASCADE")
            await self._add_column_if_not_exists(conn, "chat_history", "user_id",
                "ALTER TABLE chat_history ADD COLUMN user_id UUID REFERENCES users(id) ON DELETE CASCADE")

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_id
                ON chat_sessions(user_id)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_history_user_id
                ON chat_history(user_id)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_sessions_document_id
                ON chat_sessions(document_id)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_sessions_updated_at
                ON chat_sessions(updated_at DESC)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_history_document_id
                ON chat_history(document_id)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_history_session_id
                ON chat_history(session_id)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_documents_user_id
                ON documents(user_id)
            """)

            # pgvector index for embedding similarity search
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding
                ON document_chunks
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100)
            """)

            # Ensure embedding column exists with correct dimension
            await self._ensure_embedding_column(conn)

    async def _ensure_embedding_column(self, conn):
        """Ensure embedding column exists with correct type and dimension."""
        expected_dim = settings.EMBEDDING_DIMENSION

        col_type = await conn.fetchval("""
            SELECT data_type FROM information_schema.columns
            WHERE table_name = 'document_chunks' AND column_name = 'embedding'
        """)
        if col_type is None:
            await conn.execute(f"""
                ALTER TABLE document_chunks
                ADD COLUMN embedding vector({expected_dim})
            """)
            logger.info(f"Added embedding column vector({expected_dim}) to document_chunks")
            return

        # Column exists — check its dimension
        actual_dim = await conn.fetchval("""
            SELECT coalesce(
                (SELECT atttypmod - 4 FROM pg_attribute
                 WHERE attrelid = 'document_chunks'::regclass
                   AND attname = 'embedding'),
                0
            )
        """)
        if actual_dim and actual_dim != expected_dim:
            logger.warning(
                f"Resizing embedding column from {actual_dim}d to {expected_dim}d"
            )
            await conn.execute(f"""
                ALTER TABLE document_chunks
                ALTER COLUMN embedding TYPE vector({expected_dim})
                USING embedding::vector({expected_dim})
            """)
            logger.info(f"Embedding column resized to vector({expected_dim})")

    async def _add_column_if_not_exists(self, conn, table: str, column: str, alter_stmt: str):
        """Idempotent column addition"""
        exists = await conn.fetchval("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = $1 AND column_name = $2
        """, table, column)
        if not exists:
            await conn.execute(alter_stmt)

    async def close(self):
        """Close database connection pool"""
        if self.pool:
            await self.pool.close()

    async def update_document_status(
        self,
        document_id: str,
        status: str,
        error_message: Optional[str] = None,
        pdf_type: Optional[str] = None
    ):
        """Update document status"""
        if not self.pool:
            await self.connect()

        async with self.pool.acquire() as conn:
            query = """
                UPDATE documents
                SET
                    status = $1::varchar,
                    error_message = $2,
                    pdf_type = COALESCE($3, pdf_type),
                    processed_at = CASE
                        WHEN $1::varchar = 'completed' THEN NOW()
                        ELSE processed_at
                    END
                WHERE id = $4
            """
            await conn.execute(query, status, error_message, pdf_type, document_id)

    async def save_document_outputs(
        self,
        document_id: str,
        markdown_path: str,
        json_path: str,
        images_folder: str
    ):
        """Save document output paths"""
        if not self.pool:
            await self.connect()

        async with self.pool.acquire() as conn:
            query = """
                INSERT INTO document_outputs (document_id, markdown_path, json_path, images_folder)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (document_id)
                DO UPDATE SET
                    markdown_path = EXCLUDED.markdown_path,
                    json_path = EXCLUDED.json_path,
                    images_folder = EXCLUDED.images_folder
            """
            await conn.execute(query, document_id, markdown_path, json_path, images_folder)

    async def save_chunks(self, chunks: List[Dict]):
        """Save document chunks with optional embeddings."""
        if not self.pool:
            await self.connect()

        import json as json_lib

        expected_dim = settings.EMBEDDING_DIMENSION
        saved_count = 0
        skipped_count = 0

        print(f"[DB] save_chunks: preparing to save {len(chunks)} chunks (expected dim={expected_dim})")

        async with self.pool.acquire() as conn:
            query = """
                INSERT INTO document_chunks
                (document_id, chunk_index, content, chunk_type, metadata, embedding)
                VALUES ($1, $2, $3, $4, $5, $6)
            """

            for i, chunk in enumerate(chunks):
                metadata = chunk.get("metadata", {})
                if isinstance(metadata, dict):
                    metadata = json_lib.dumps(metadata)

                embedding = chunk.get("embedding")

                if embedding is not None:
                    emb_len = len(embedding)
                    if emb_len != expected_dim:
                        logger.warning(
                            f"[DB] save_chunks: chunk {i} dim mismatch: got {emb_len}d, "
                            f"expected {expected_dim}d — saving without embedding"
                        )
                        embedding = None
                    else:
                        embedding = convert_embedding_to_pgvector(embedding)

                try:
                    await conn.execute(
                        query,
                        chunk.get("document_id"),
                        chunk.get("chunk_index"),
                        chunk.get("content"),
                        chunk.get("chunk_type", "text"),
                        metadata,
                        embedding,
                    )
                    saved_count += 1
                    if embedding is not None:
                        skipped_count += 1
                except Exception as e:
                    print(f"[DB] save_chunks: ERROR saving chunk {i} - {e}")
                    raise

        print(f"[DB] save_chunks: completed — {saved_count} chunks saved, "
              f"{skipped_count} with embeddings")

    async def update_chunk_embedding(
        self, chunk_id: str, embedding: List[float]
    ):
        """Update embedding vector for a single chunk (pgvector string format)."""
        if not self.pool:
            await self.connect()

        expected_dim = settings.EMBEDDING_DIMENSION
        emb_len = len(embedding)
        if emb_len != expected_dim:
            logger.warning(
                f"[DB] update_chunk_embedding: dim mismatch: got {emb_len}d, "
                f"expected {expected_dim}d — skipping"
            )
            return

        pgvec = convert_embedding_to_pgvector(embedding)
        logger.info(
            f"[DB] update_chunk_embedding: chunk={chunk_id}, dim={emb_len}, "
            f"first_3={embedding[:3]}"
        )

        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE document_chunks SET embedding = $1::vector WHERE id = $2",
                pgvec,
                chunk_id,
            )
            logger.info(f"[DB] update_chunk_embedding: updated chunk {chunk_id}")

    async def search_similar_chunks(
        self,
        document_id: str,
        query_embedding: List[float],
        top_k: int = 5,
        min_similarity: float = 0.5,
    ) -> List[Dict]:
        """Search for similar chunks using cosine similarity (pgvector)."""
        if not self.pool:
            await self.connect()

        if not document_id or not query_embedding:
            print("[DB] search_similar_chunks: empty document_id or query_embedding")
            return []

        pgvec = convert_embedding_to_pgvector(query_embedding)

        async with self.pool.acquire() as conn:
            query = """
                SELECT
                    id, document_id, chunk_index, content, chunk_type, metadata,
                    1 - (embedding <=> $2::vector) AS similarity
                FROM document_chunks
                WHERE document_id = $1::uuid
                  AND embedding IS NOT NULL
                  AND 1 - (embedding <=> $2::vector) >= $3
                ORDER BY embedding <=> $2::vector
                LIMIT $4
            """
            try:
                rows = await conn.fetch(
                    query, document_id, pgvec, min_similarity, top_k
                )
                results = [dict(row) for row in rows]
                logger.info(
                    f"[DB] search_similar_chunks: found {len(results)} chunks for "
                    f"document {document_id} (min_sim={min_similarity})"
                )
                for r in results:
                    logger.info(
                        f"  chunk {r.get('chunk_index')}: "
                        f"similarity={r.get('similarity', 0):.4f}"
                    )
                return results
            except Exception as e:
                logger.error(f"[DB] search_similar_chunks: ERROR - {e}", exc_info=True)
                return []

    async def update_queue_status(
        self,
        document_id: str,
        status: str,
        error_message: Optional[str] = None
    ):
        """Update processing queue status"""
        if not self.pool:
            await self.connect()

        async with self.pool.acquire() as conn:
            query = """
                UPDATE processing_queue
                SET status = $1,
                    error_message = $2,
                    started_at = CASE WHEN $1 = 'processing' THEN NOW() ELSE started_at END,
                    completed_at = CASE WHEN $1 IN ('completed', 'failed') THEN NOW() ELSE completed_at END
                WHERE document_id = $3
            """
            await conn.execute(query, status, error_message, document_id)

    async def get_document(self, document_id: str) -> Optional[Dict]:
        """Get document by ID"""
        if not self.pool:
            await self.connect()

        async with self.pool.acquire() as conn:
            query = """
                SELECT d.*, do.markdown_path, do.json_path, do.images_folder
                FROM documents d
                LEFT JOIN document_outputs do ON d.id = do.document_id
                WHERE d.id = $1
            """
            row = await conn.fetchrow(query, document_id)
            return dict(row) if row else None

    async def get_chunks(self, document_id: str) -> List[Dict]:
        """Get document chunks (sequential, without embeddings)."""
        if not self.pool:
            await self.connect()

        if not document_id:
            print(f"[DB] get_chunks: empty document_id, returning empty list")
            return []

        async with self.pool.acquire() as conn:
            query = """
                SELECT id, document_id, chunk_index, content, chunk_type, metadata, created_at
                FROM document_chunks
                WHERE document_id = $1::uuid
                ORDER BY chunk_index
            """
            try:
                rows = await conn.fetch(query, document_id)
                print(f"[DB] get_chunks: found {len(rows)} rows")
                return [dict(row) for row in rows]
            except Exception as e:
                print(f"[DB] get_chunks: ERROR with UUID cast - {e}")
                query2 = """
                    SELECT id, document_id, chunk_index, content, chunk_type, metadata, created_at
                    FROM document_chunks
                    WHERE document_id = $1
                    ORDER BY chunk_index
                """
                rows = await conn.fetch(query2, document_id)
                print(f"[DB] get_chunks: found {len(rows)} rows (no cast)")
                return [dict(row) for row in rows]

    async def save_chat_message(
        self,
        document_id: Optional[str],
        session_id: str,
        role: str,
        message: str
    ):
        """Save chat message"""
        if not self.pool:
            await self.connect()

        doc_id = document_id if document_id else None

        async with self.pool.acquire() as conn:
            query = """
                INSERT INTO chat_history (document_id, session_id, role, message)
                VALUES ($1, $2, $3, $4)
            """
            await conn.execute(query, doc_id, session_id, role, message)

    async def get_chat_history(
        self,
        document_id: str,
        session_id: str,
        limit: int = 50
    ) -> List[Dict]:
        """Get chat history"""
        if not self.pool:
            await self.connect()

        async with self.pool.acquire() as conn:
            query = """
                SELECT * FROM chat_history
                WHERE session_id = $1
                ORDER BY created_at DESC
                LIMIT $2
            """
            rows = await conn.fetch(query, session_id, limit)
            return [dict(row) for row in reversed(rows)]

    async def get_documents_without_chunks(self) -> List[Dict]:
        """Get documents that have no chunks - for reprocessing"""
        if not self.pool:
            await self.connect()

        async with self.pool.acquire() as conn:
            query = """
                SELECT d.id, d.filename, d.status
                FROM documents d
                LEFT JOIN document_chunks dc ON d.id = dc.document_id
                WHERE dc.id IS NULL AND d.status = 'completed'
                LIMIT 20
            """
            rows = await conn.fetch(query)
            return [dict(row) for row in rows]


import logging
logger = logging.getLogger(__name__)
