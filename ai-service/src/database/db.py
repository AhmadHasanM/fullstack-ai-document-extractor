import asyncpg
from typing import Optional, Dict, List
from datetime import datetime
from ..config import settings


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
            # Auto-create tables if they don't exist
            await self._ensure_tables()

    async def _ensure_tables(self):
        """Create tables if they don't exist"""
        async with self.pool.acquire() as conn:
            # Create chat_sessions table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    document_id UUID REFERENCES documents(id) ON DELETE SET NULL,
                    title VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create chat_history table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
                    session_id UUID REFERENCES chat_sessions(id) ON DELETE CASCADE,
                    role VARCHAR(20) CHECK (role IN ('user', 'assistant')),
                    message TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create indexes
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
        """Save document chunks"""
        if not self.pool:
            await self.connect()

        import json as json_lib
        import logging
        logger = logging.getLogger(__name__)

        print(f"[DB] save_chunks: preparing to save {len(chunks)} chunks")

        async with self.pool.acquire() as conn:
            query = """
                INSERT INTO document_chunks
                (document_id, chunk_index, content, chunk_type, metadata)
                VALUES ($1, $2, $3, $4, $5)
            """

            for i, chunk in enumerate(chunks):
                # Convert metadata dict to JSON string for PostgreSQL JSONB
                metadata = chunk.get("metadata", {})
                if isinstance(metadata, dict):
                    metadata = json_lib.dumps(metadata)

                try:
                    await conn.execute(
                        query,
                        chunk.get("document_id"),
                        chunk.get("chunk_index"),
                        chunk.get("content"),
                        chunk.get("chunk_type", "text"),
                        metadata
                    )
                    print(f"[DB] save_chunks: saved chunk {i} for doc {chunk.get('document_id')}")
                except Exception as e:
                    print(f"[DB] save_chunks: ERROR saving chunk {i} - {e}")
                    raise

        print(f"[DB] save_chunks: completed successfully")

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
        """Get document chunks"""
        if not self.pool:
            await self.connect()

        # Handle empty string
        if not document_id:
            print(f"[DB] get_chunks: empty document_id, returning empty list")
            return []

        print(f"[DB] get_chunks: querying for document_id={document_id}")

        # Try as UUID first
        async with self.pool.acquire() as conn:
            query = """
                SELECT * FROM document_chunks
                WHERE document_id = $1::uuid
                ORDER BY chunk_index
            """
            try:
                rows = await conn.fetch(query, document_id)
                print(f"[DB] get_chunks: found {len(rows)} rows")
                return [dict(row) for row in rows]
            except Exception as e:
                print(f"[DB] get_chunks: ERROR with UUID cast - {e}")
                # Try without cast
                query2 = """
                    SELECT * FROM document_chunks
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

        # Handle None/empty document_id as NULL
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