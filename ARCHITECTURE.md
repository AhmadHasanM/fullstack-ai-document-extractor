# Fullstack AI Document Extractor — Technical Architecture

> Generated from source code analysis. Every statement below is grounded in actual code.

---

## Table of Contents

1.  [How Everything Connects](#1-how-everything-connects)
2.  [Authentication & Authorization](#2-authentication--authorization)
3.  [Backend Architecture](#3-backend-architecture)
4.  [Database Analysis](#4-database-analysis)
5.  [AI Service Architecture](#5-ai-service-architecture)
6.  [Frontend Architecture](#6-frontend-architecture)
7.  [File Processing & Storage](#7-file-processing--storage)
8.  [Security Audit](#8-security-audit)
9.  [Performance Analysis](#9-performance-analysis)
10. [Deployment & Infrastructure](#10-deployment--infrastructure)
11. [Code Quality Review](#11-code-quality-review)
12. [Full Request Lifecycle Diagrams](#12-full-request-lifecycle-diagrams)
13. [Critical Security Observations](#13-critical-security-observations)
14. [Top 10 Technical Risks](#14-top-10-technical-risks)
15. [Top 10 Improvement Priorities](#15-top-10-improvement-priorities)

---

## 1. How Everything Connects

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DOCKER COMPOSE                               │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌─────────────────┐ │
│  │ Frontend │──▶│ Backend  │──▶│ AI Serv. │──▶│ PostgreSQL      │ │
│  │ :3000    │   │ :8080    │   │ :8000    │   │ (pgvector) :5432│ │
│  │ Next.js  │   │ Gin      │   │ FastAPI  │   │                 │ │
│  └──────────┘   └────┬─────┘   └────┬─────┘   └─────────────────┘ │
│                      │               │                             │
│                      │               └──────▶ RabbitMQ :5672       │
│                      └──────────────────────▶ RabbitMQ :5672       │
└─────────────────────────────────────────────────────────────────────┘
```

### Services

| Service | Tech | Port | Purpose |
|---------|------|------|---------|
| `ai_frontend` | Next.js 16 + React 19 + Tailwind 4 | 3000 | UI |
| `ai_backend` | Go 1.25 + Gin + lib/pq | 8080 | API gateway, auth, file serving |
| `ai_service` | Python 3.11 + FastAPI + asyncpg | 8000 | PDF processing, embeddings, RAG |
| `ai_postgres` | PostgreSQL 16 + pgvector | 5432 | Data + vector storage |
| `ai_rabbitmq` | RabbitMQ 3 | 5672,15672 | Async job queue |

### Data Flow (Upload → Chat)

```
User uploads PDF
  → Frontend POST /api/upload (multipart)
  → Backend saves file, inserts DB record, publishes RabbitMQ message
  → AI Service consumer receives message
  → PDFProcessor.process() runs (detect → extract → OCR → tables → images → markdown → chunk → embed)
  → Chunks + embeddings saved to DB
  → User asks question in chat
  → Frontend POST /api/chat/sessions/:id/messages
  → Backend proxies to AI Service POST /api/v1/chat
  → AI Service QAService retrieves relevant chunks via pgvector similarity
  → Constructs prompt with context → calls Gemini → returns response
  → Backend saves user + assistant messages → returns to frontend
```

---

## 2. Authentication & Authorization

### 2.1 JWT Algorithm

- **Algorithm**: HS256 (HMAC-SHA256) — `backend/internal/handlers/auth.go:183`
  ```go
  token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
  ```
- **Signing key**: `cfg.JWTSecret` — must be set via `JWT_SECRET` env var.
- **Validation**: `backend/internal/middleware/auth.go:47-52`
  ```go
  token, err := jwt.Parse(tokenString, func(token *jwt.Token) (interface{}, error) {
      if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
          return nil, jwt.ErrSignatureInvalid
      }
      return []byte(cfg.JWTSecret), nil
  })
  ```
  Explicitly checks HMAC signing method (prevents algorithm confusion attacks).

### 2.2 JWT Expiry

- **24 hours** — `backend/internal/handlers/auth.go:174`
  ```go
  expirationTime := time.Now().Add(24 * time.Hour)
  ```
- **No refresh token mechanism exists.** When the token expires, the user must log in again.
- The `exp` claim is set as Unix timestamp: `backend/internal/handlers/auth.go:179`

### 2.3 Token Claims

```go
claims := jwt.MapClaims{
    "user_id": user.ID,     // UUID string
    "email":   user.Email,
    "exp":     expirationTime.Unix(),
    "iat":     time.Now().Unix(),
}
```
No `jti` (token ID), no `nbf` (not before), no role/permission claims.

### 2.4 Middleware Validation

**`AuthMiddleware`** (`backend/internal/middleware/auth.go:14-86`):

1. Check `cfg.JWTSecret != ""` — fail with 500 if blank
2. Extract `Authorization: Bearer <token>` header
3. Split on space, verify exactly 2 parts
4. Parse JWT with HMAC signing check
5. Extract `user_id` from claims as string
6. Set `c.Set("user_id", userID)` — propagates to handlers via `c.GetString("user_id")`
7. Calls `c.Next()` on success, `c.Abort()` with JSON error on failure

**`OptionalAuthMiddleware`** (`backend/internal/middleware/auth.go:88-125`):
- Same logic but does not abort on missing/invalid token
- Only sets `user_id` if valid token present
- Used by `GetChatHistory` and `GetSessionHistory`

### 2.5 Token Storage (Frontend)

```typescript
// frontend/src/lib/auth.tsx
localStorage.setItem("auth_token", data.token);
localStorage.setItem("auth_user", JSON.stringify(data.user));
```

- Token stored in **localStorage** (not httpOnly cookies)
- Auto-attached via `authFetch()` helper:
  ```typescript
  const token = localStorage.getItem("auth_token");
  headers["Authorization"] = `Bearer ${token}`;
  ```
- **Note**: The chat page (`frontend/src/app/(dashboard)/chat/page.tsx`) bypasses `authFetch()` and manually reads the token from localStorage and sets the Authorization header. The dashboard page, history page, and file detail page use `authFetch()`.

### 2.6 Ownership Validation

- Every document query filters by `user_id`:
  ```go
  // backend/internal/database/postgres.go:94
  WHERE id = $1 AND user_id = $2
  ```
- Chat sessions also filtered: `backend/internal/database/postgres.go:322`
- DeleteDocument enforces ownership: `backend/internal/database/postgres.go:152-156`
- **Risk**: `GetChatHistory` has a branch without user filter:
  ```go
  // backend/internal/database/postgres.go:248
  WHERE document_id = $1  // No user_id filter!
  ```
  This path is taken when `sessionID == ""`, allowing any authenticated user to read chat history for any document_id.

### 2.7 Registration Flow

1. `POST /api/auth/register` with `{email, password, name?}`
2. Validate password >= 8 chars
3. Check if email exists (`GetUserByEmail`)
4. Hash password with bcrypt (default cost)
5. Create user record
6. Generate JWT token
7. Return `{token, user: {id, email, name, created_at, updated_at}}`

### 2.8 Login Flow

1. `POST /api/auth/login` with `{email, password}`
2. Fetch user by email
3. Compare bcrypt hash
4. Generate JWT token
5. Return same shape as register

### 2.9 Me Endpoint

`GET /api/auth/me` — reads `user_id` from JWT claims (set by middleware), fetches full user record from DB.

---

## 3. Backend Architecture

### 3.1 Directory Structure

```
backend/
├── cmd/api/main.go              — Entrypoint, router setup
├── internal/
│   ├── config/config.go         — Env-driven config (validates JWT_SECRET)
│   ├── database/postgres.go     — All SQL queries (no ORM)
│   ├── handlers/
│   │   ├── auth.go              — Register, Login, Me, generateToken
│   │   ├── document.go          — CRUD + serving outputs
│   │   ├── uploads.go           — File upload + queue publish
│   │   ├── chat.go              — Chat sessions + message proxying
│   │   └── queue.go             — Queue status endpoints
│   ├── middleware/
│   │   ├── auth.go              — JWT validation
│   │   ├── cors.go              — CORS with origin whitelist
│   │   ├── ratelimit.go         — In-memory IP-based rate limiter
│   │   ├── security.go          — Security headers
│   │   └── logger.go            — Request logging
│   ├── models/models.go         — All struct types
│   └── queue/rabbitmq.go        — RabbitMQ connection + publish
└── Dockerfile
```

### 3.2 Request Lifecycle

```
HTTP Request
  → Gin Engine
    → CORSMiddleware (origin check)
    → LoggerMiddleware (method, path, status, duration)
    → SecurityHeadersMiddleware (CSP, HSTS, etc.)
    → RateLimiter.Limit() (if configured for route)
    → AuthMiddleware (JWT parse, set user_id)
    → Handler (business logic)
    → Database query (user_id filtered)
    → JSON Response
```

### 3.3 Middleware Order

Applied in `main.go` in this order:

```go
router.Use(middleware.CORSMiddleware(cfg.CORSAllowedOrigins))      // 1
router.Use(middleware.LoggerMiddleware())                            // 2
router.Use(middleware.SecurityHeadersMiddleware(cfg.IsProduction))   // 3
```

Then per-group:
```go
api.POST("/auth/register", authRateLimiter.Limit(), authHandler.Register)  // 4
protected.Use(middleware.AuthMiddleware(cfg))                                // 5
protected.POST("/upload", uploadRateLimiter.Limit(), uploadHandler.Upload)  // 6
```

### 3.4 Rate Limiter Implementation

**File**: `backend/internal/middleware/ratelimit.go`

- **Type**: In-memory, IP-based, sliding window
- **Data structure**: `map[string]*visitor` protected by `sync.Mutex`
- **Instances**:
  - Auth: 10 requests/minute
  - Chat: 30 requests/minute
  - Upload: 10 requests/minute
- **Implementation**: Count increments on each request within the time window. When count exceeds max, returns 429 with `Retry-After: 60` header.
- **Cleanup**: Background goroutine (`cleanup()`) runs every minute, removing expired entries.
- **Limitations**:
  - Not distributed (in-memory per instance — breaks with multiple replicas)
  - IP-based (behind reverse proxy, all traffic appears as same IP unless proxy forwards `X-Forwarded-For`)
  - No rate limit on `GET /api/documents`, `GET /api/chat/sessions` — unbounded reads

### 3.5 CORS Implementation

**File**: `backend/internal/middleware/cors.go`

- Reads `CORS_ALLOWED_ORIGINS` env var (comma-separated)
- Builds origin whitelist map
- Responds to `OPTIONS` preflight with 204
- Sets headers: `Access-Control-Allow-Origin`, `Allow-Methods`, `Allow-Headers`, `Allow-Credentials`
- Falls back to `*` if whitelist contains exactly `*`

### 3.6 Security Headers

**File**: `backend/internal/middleware/security.go`

```go
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: strict-origin-when-cross-origin
Content-Security-Policy: default-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob:; script-src 'self' 'unsafe-eval' 'unsafe-inline'; connect-src 'self' *;
Strict-Transport-Security: max-age=31536000; includeSubDomains  // only in production
```

**CSP issues**: `script-src 'unsafe-eval' 'unsafe-inline'` weakens XSS protection significantly. `connect-src *` allows API calls to any domain.

### 3.7 Error Handling Strategy

- All handlers return JSON error responses using `models.ErrorResponse{Error, Message}`
- Consistent error codes: `bad_request`, `unauthorized`, `not_found`, `server_error`, `conflict`, `invalid_file_type`, `file_too_large`
- Internal server errors use generic messages ("Registration failed", "Failed to delete document") — no stack traces leaked
- **No centralized error handler** — each route has its own try/catch block
- **No panic recovery middleware** — a panic would crash the server (Gin has built-in Recovery middleware but it's not explicitly configured in `main.go`)

### 3.8 Queue System Flow

```
Backend POST /api/upload
  → Create DB record (status=pending)
  → Insert processing_queue row (status=queued)
  → Publish JSON to RabbitMQ queue "pdf_processing_queue"
  → Return 200 to user

AI Service (daemon thread on startup)
  → QueueConsumer connects via pika BlockingConnection
  → basic_consume with auto-ack (Wait — it uses basic_ack in callback)
  → On message:
    → basic_ack immediately
    → Spawn daemon thread
    → New asyncio event loop
    → Run PDFProcessor.process()
    → Update DB status (processing → completed/failed)
```

**File**: `backend/internal/queue/rabbitmq.go`
- Queue declared as durable, non-exclusive, non-auto-delete
- Messages published with `Persistent` delivery mode
- Priority mapped from `msg.Priority`

**File**: `ai-service/src/services/queue_consumer.py`
- Uses blocking pika (not async)
- `prefetch_count=1` — processes one message at a time per consumer
- **Acks before processing** — if the AI service crashes mid-processing, the message is lost (no redelivery)
- Each message spawns a new `threading.Thread` with its own asyncio event loop — no backpressure control

### 3.9 File Serving Mechanism

- `GET /api/documents/:id/markdown` — reads from `outputs/markdown/<id>.md`, serves via `c.File()`
- `GET /api/documents/:id/json` — reads from `outputs/json/<id>.json`, serves via `c.File()`
- `GET /api/documents/:id/images` — lists directory `outputs/images/<id>/`, returns filenames
- Images are served directly via: `${API}/outputs/images/${docId}/${img}` (from frontend)
- Path traversal protection via `isPathSafe()` — checks for `..` in path
- **No authentication on image URLs** — anyone who knows an image path can access it

### 3.10 Document Deletion Flow

**File**: `backend/internal/handlers/document.go:87-141`

1. Extract `user_id` from JWT
2. `GetDocument(id, userID)` — verifies ownership
3. `os.Remove(doc.FilePath)` — delete uploaded PDF
4. `GetDocumentOutput(id)` — get output paths
5. `os.Remove(markdownPath + jsonPath + os.RemoveAll(imagesFolder))`
6. `DeleteDocumentChatSessions(id, userID)` — manually deletes chat sessions
7. `DeleteDocument(id, userID)` — DB delete cascades to chunks, outputs, elements, queue, chat_history

---

## 4. Database Analysis

### 4.1 All Tables and Relationships

```sql
-- init.sql + runtime migrations from postgres.go + db.py

users
├── id UUID PK
├── email VARCHAR(255) UNIQUE
├── password_hash VARCHAR(255)
├── name VARCHAR(255)
├── created_at, updated_at TIMESTAMP

documents
├── id UUID PK
├── user_id UUID → users(id) ON DELETE CASCADE          ← added by migration
├── filename, original_filename VARCHAR(255)
├── file_path TEXT
├── file_size BIGINT
├── pdf_type VARCHAR(20) CHECK (digital,scanned,mixed)
├── status VARCHAR(20) CHECK (pending,processing,completed,failed)
├── error_message TEXT
├── created_at, updated_at, processed_at TIMESTAMP

document_outputs
├── id UUID PK
├── document_id UUID → documents(id) ON DELETE CASCADE
├── markdown_path, json_path, images_folder TEXT
├── created_at TIMESTAMP

document_chunks
├── id UUID PK
├── document_id UUID → documents(id) ON DELETE CASCADE
├── chunk_index INTEGER
├── content TEXT
├── embedding vector(768)        ← pgvector
├── page_number INTEGER
├── chunk_type VARCHAR(50)
├── metadata JSONB
├── created_at TIMESTAMP

processing_queue
├── id UUID PK
├── document_id UUID → documents(id) ON DELETE CASCADE
├── priority INTEGER
├── status VARCHAR CHECK (queued,processing,completed,failed)
├── retry_count, max_retries INTEGER
├── error_message TEXT
├── created_at, started_at, completed_at TIMESTAMP

extracted_elements
├── id UUID PK
├── document_id UUID → documents(id) ON DELETE CASCADE
├── element_type VARCHAR(50)
├── content TEXT
├── page_number, position_index INTEGER
├── metadata JSONB
├── created_at TIMESTAMP

chat_sessions
├── id UUID PK
├── user_id UUID → users(id) ON DELETE CASCADE
├── document_id UUID → documents(id) ON DELETE SET NULL
├── title VARCHAR(255)
├── created_at, updated_at TIMESTAMP

chat_history
├── id UUID PK
├── user_id UUID → users(id) ON DELETE CASCADE
├── document_id UUID → documents(id) ON DELETE CASCADE
├── session_id UUID → chat_sessions(id) ON DELETE CASCADE
├── role VARCHAR CHECK (user,assistant)
├── message TEXT
├── created_at TIMESTAMP
```

### 4.2 Foreign Key Behavior

| Source | Target | ON DELETE | Effect |
|--------|--------|-----------|--------|
| documents.user_id | users.id | CASCADE | Delete user → delete all their docs |
| document_outputs.document_id | documents.id | CASCADE | Delete doc → delete outputs |
| document_chunks.document_id | documents.id | CASCADE | Delete doc → delete chunks |
| processing_queue.document_id | documents.id | CASCADE | Delete doc → delete queue item |
| extracted_elements.document_id | documents.id | CASCADE | Delete doc → delete elements |
| chat_sessions.user_id | users.id | CASCADE | Delete user → delete sessions |
| chat_sessions.document_id | documents.id | SET NULL | Delete doc → nullify session doc ref |
| chat_history.user_id | users.id | CASCADE | Delete user → delete history |
| chat_history.document_id | documents.id | CASCADE | Delete doc → delete history |
| chat_history.session_id | chat_sessions.id | CASCADE | Delete session → delete history |

### 4.3 Indexes

```sql
documents(user_id)
documents(status)
documents(created_at DESC)
document_chunks(document_id)
document_chunks(chunk_type)
document_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)
processing_queue(status)
processing_queue(priority DESC)
extracted_elements(document_id)
extracted_elements(element_type)
chat_sessions(user_id)
chat_sessions(document_id)
chat_sessions(updated_at DESC)
chat_history(user_id)
chat_history(document_id)
chat_history(session_id)
users(email)
```

### 4.4 Query Optimization Observations

- **Missing compound index**: `documents(user_id, status)` would speed up the dashboard stats query (`GROUP BY status WHERE user_id = $1`)
- **Missing compound index**: `document_chunks(document_id, embedding)` — the vector search query has `WHERE document_id = $1 AND embedding IS NOT NULL`. The current index is only on `embedding` via ivfflat.
- **Missing index**: `processing_queue(document_id)` — used by `GetQueueStatus` and `update_queue_status`
- `get_chunks` in `db.py` has a fallback: tries `WHERE document_id = $1::uuid` first, catches error, retries with `WHERE document_id = $1` — this indicates UUID casting issues
- The Go `ListDocuments` does not `SELECT file_path` (it's excluded), so the `FilePath` field won't be populated in list view

### 4.5 Migration Strategy

- **`init.sql`** — runs once on first database creation via Docker volume mount
- **Go migration** (`postgres.go:36-73`) — idempotent `CREATE TABLE IF NOT EXISTS`, then `DO $$ BEGIN` blocks to add columns
- **Python migration** (`db.py:23-94`) — separately creates tables again with `CREATE TABLE IF NOT EXISTS`, adds columns, creates indexes
- **Risk**: Multiple migration points (init.sql + Go + Python) can diverge. The Go side only has 2 migration steps (adding user_id columns); the Python side has a full table creation block

### 4.6 pgvector Usage

- **Column type**: `vector(768)` — defined in init.sql, created by Python db.py, checked/altered by recent fix
- **Index**: IVFFlat with 100 lists, using `vector_cosine_ops`
- **Search query**:
  ```sql
  1 - (embedding <=> $2::vector) AS similarity
  WHERE document_id = $1::uuid
    AND embedding IS NOT NULL
    AND 1 - (embedding <=> $2::vector) >= $3
  ORDER BY embedding <=> $2::vector
  LIMIT $4
  ```
- **Insert format**: Must be string `"[0.1,0.2,0.3]"` (asyncpg requirement)
- **Dimension**: 768 (all-mpnet-base-v2 / text-embedding-004)

---

## 5. AI Service Architecture

### 5.1 File Structure

```
ai-service/
├── main.py                        — FastAPI app, lifespan, consumer thread
├── src/
│   ├── config.py                  — Pydantic Settings (reads .env)
│   ├── api/routes.py              — FastAPI router (chat, sessions, chunks)
│   ├── database/db.py             — asyncpg operations
│   ├── extractors/
│   │   ├── pdf_detector.py        — Digital/scanned/mixed detection
│   │   ├── text_extractor.py      — PyMuPDF text extraction, heading detection
│   │   ├── table_extractor.py     — Table Transformer + pdfplumber fallback
│   │   ├── image_extractor.py     — PyMuPDF image extraction, page rendering
│   │   ├── ocr_processor.py       — Surya OCR for scanned pages
│   │   └── pdf_processor.py       — Main orchestrator
│   └── services/
│       ├── document_chunker.py    — Paragraph + section chunking
│       ├── embedding_service.py   — Gemini + sentence-transformers
│       ├── markdown_formatter.py  — Gemini-based markdown formatting
│       ├── qa_service.py          — RAG: vector search → prompt → Gemini
│       └── queue_consumer.py      — RabbitMQ consumer (blocking pika)
```

### 5.2 PDF Processing Pipeline (Step-by-Step)

**File**: `ai-service/src/extractors/pdf_processor.py` — `process()` method

```
Step 1: Detect PDF type (detect_type)
Step 2: Extract content based on type:
  - digital: PyMuPDF text + pdfplumber tables
  - scanned: pages→PNG→Surya OCR + table extraction
  - mixed: digital first, OCR for low-text pages
Step 3: Extract images (PyMuPDF get_images)
Step 4: Generate markdown (Gemini or basic fallback)
Step 5: Save outputs (markdown + JSON files)
Step 6: Chunk document (paragraph-based, configurable size/overlap)
Step 7: Generate embeddings for each chunk
Step 8: Save chunks + embeddings to DB
```

### 5.3 Digital vs Scanned Detection

**File**: `ai-service/src/extractors/pdf_detector.py`

- Opens PDF with PyMuPDF, iterates all pages
- Criteria for "has text": `page.get_text().strip()` with length > 50 chars
- Criteria for "has images": `page.get_images()` returns non-empty
- Decision:
  - `text_percentage > 80%` → "digital"
  - `text_percentage < 20% AND image_percentage > 50%` → "scanned"
  - Otherwise → "mixed"

### 5.4 OCR Flow

**File**: `ai-service/src/extractors/ocr_processor.py`

- Uses **Surya OCR** (local, no API key needed)
- Lazy loads: `FoundationPredictor` → `DetectionPredictor` → `RecognitionPredictor`
- Only used for scanned PDFs or low-text pages in mixed PDFs
- **Table extraction from OCR**: naive heuristic — splits by double spaces, groups into columns. No AI table detection on OCR output.

### 5.5 Markdown Generation

**File**: `ai-service/src/services/markdown_formatter.py`

Two paths:
1. **Gemini path** (if `GEMINI_API_KEY` set):
   - Builds content summary from raw text + tables + images
   - Sends to Gemini 2.5 Flash via `generate_content()` with strict formatting prompt
   - Falls back to basic format if Gemini fails
2. **Basic fallback**:
   - `# Document` header
   - `## Page N` per page
   - Tables formatted as markdown
   - Images as `![filename](path)`

### 5.6 Chunking Strategy

**File**: `ai-service/src/services/document_chunker.py`

- **Type**: Fixed-size with overlap (paragraph-aware)
- **Chunk size**: 1000 characters (configurable)
- **Overlap**: 200 characters (configurable)
- **Algorithm**:
  1. Split text by `\n\n` (paragraphs)
  2. Iterate paragraphs, accumulate until chunk_size exceeded
  3. On overflow: save current chunk, start new chunk with overlap text
  4. At end: save remaining as final chunk
- **Alternative method**: `chunk_by_sections()` — splits by markdown headings — available but NOT called by the main pipeline
- **Chunk metadata**: `has_table`, `has_list`, `has_code`, `has_formula`, `word_count` — extracted but NOT saved to DB (only `chunk_type: "text"` is saved)

### 5.7 Embedding System

**File**: `ai-service/src/services/embedding_service.py`

- **Providers**: Gemini (`models/text-embedding-004`) or sentence-transformers (`all-mpnet-base-v2`)
- **Provider selection**: configurable via `EMBEDDING_PROVIDER` env var: `"gemini"`, `"sentence-transformers"`, or `"auto"` (try Gemini first, fallback to sentence-transformers)
- **Dimension**: 768 (both models)
- **Batching**: processes one text at a time (per-text API call for Gemini)
- **Fallback**: if Gemini fails and provider is `"auto"`, falls back to sentence-transformers
- **Query embedding**: same method as document embeddings — `generate_embeddings_batch([query])`

### 5.8 Vector Search (RAG Retrieval)

**File**: `ai-service/src/services/qa_service.py:67-116`

1. Generate query embedding via `embedding_service.generate_query_embedding(question)`
2. If embedding succeeds → `search_similar_chunks()` with:
   - Cosine similarity (`<=>` operator)
   - `TOP_K_RESULTS=5` (configurable)
   - `MIN_SIMILARITY=0.5` threshold
3. If vector search returns results → build context string
4. **Fallback**: if query embedding fails OR vector search returns 0 results → fetch chunks sequentially (`get_chunks()`) and use first `top_k` chunks
5. Build context string from chunks with relevance scores, truncated to `MAX_CONTEXT_CHARS=10000`

### 5.9 RAG Pipeline (End-to-End)

```
User question
  → Backend POST /api/chat/sessions/:id/messages
  → Backend saves user message to DB
  → Backend HTTP POST to AI Service /api/v1/chat
  → AI Service QAService.answer_question(document_id, question)
    → Sanitize input (strip system tokens, truncate to 4000 chars)
    → Check injection patterns
    → Retrieve relevant chunks (vector search → fallback)
    → Build prompt:
      "Answer the question based ONLY on the provided document context.
       DOCUMENT CONTEXT: {chunks}
       QUESTION: {question}
       ANSWER:"
    → Call Gemini 2.5 Flash
    → Return response text
  → Backend saves assistant message to DB
  → Backend returns response to frontend
```

### 5.10 Injection Protection

**File**: `ai-service/src/services/qa_service.py:13-24,46-65`

- Blocked patterns: `ignore all instructions`, `forget context`, `system prompt`, `<|im_start|>`, `<|im_end|>`, `<system>` tags
- Sanitization: strips known prompt-injection tokens from input
- Message length limit: 4000 characters (hardcoded)
- Backend also enforces 10000 char limit on chat messages (`chat.go:388`)

### 5.11 Context Window Handling

- Max context chars: 10,000 (`MAX_CONTEXT_CHARS` config)
- Chunks are truncated to fit within this limit, with per-chunk relevance scores shown as `[Relevance: XX%]` prefix
- If context is exhausted mid-chunk, it truncates with remaining chars (only if remaining > 200 chars)

---

## 6. Frontend Architecture

### 6.1 File Structure (App Router)

```
frontend/src/
├── app/
│   ├── layout.tsx                — Root layout
│   ├── globals.css               — Tailwind v4 global styles
│   ├── loading.tsx               — Global loading state
│   ├── (auth)/
│   │   ├── layout.tsx            — Auth layout (no sidebar)
│   │   ├── login/page.tsx
│   │   └── register/page.tsx
│   ├── (dashboard)/
│   │   ├── layout.tsx            — Dashboard layout (sidebar + nav)
│   │   ├── page.tsx              — Dashboard (upload, stats, recent files)
│   │   ├── history/page.tsx      — Document history table
│   │   ├── chat/page.tsx         — Chat UI (sidebar + messages + input)
│   │   └── file/[id]/page.tsx    — Document detail (overview, markdown, JSON, images)
├── components/
│   ├── chat/                     — ChatLayout, ChatSidebar, ChatMessages, ChatInput
│   └── history/                  — HistoryTable, HistoryCard (unused in current app)
└── lib/
    └── auth.tsx                  — AuthContext, useAuth, authFetch
```

### 6.2 Auth Flow

1. User visits `/login` → enters email/password
2. `POST /api/auth/login` → receives `{token, user}`
3. Token stored in `localStorage("auth_token")`, user in `localStorage("auth_user")`
4. `<AuthProvider>` reads token/user from localStorage on mount
5. Protected pages redirect to `/login` if no token
6. `authFetch()` wraps all API calls with `Authorization: Bearer <token>`
7. Logout clears localStorage and redirects to `/login`

### 6.3 State Management

- **No external state library** — plain React `useState` + `useEffect`
- Auth state: React Context (`AuthContext`) with `token`, `user`, `isLoading`
- Document lists: `useState<Doc[]>` with polling (`setInterval(loadData, 3000)` on dashboard)
- Chat: `useState<Message[]>, useState<ChatSession[]>, useState<Document[]>`

### 6.4 API Abstraction

- `authFetch(url, options)` — adds `Authorization` header from localStorage
- `useAuth()` hook — provides `user`, `token`, `login`, `register`, `logout`, `isAuthenticated`
- Chat page manually reads from localStorage instead of using `authFetch()` — inconsistency
- No centralized API error handling — each page handles errors individually with `console.error()` and `alert()` or inline error messages

### 6.5 Dashboard Data Flow

- Loads documents on mount and every 3 seconds (polling): `frontend/src/app/(dashboard)/page.tsx:99-103`
- Displays stats (queued, processing, completed, failed)
- Upload via drag-and-drop or file picker → `POST /api/upload` → reload data
- Shows recent 5 files as links to detail pages

### 6.6 Upload Flow

1. User drops file or clicks "Choose File"
2. `FormData` with `file` field → `POST /api/upload` via `authFetch`
3. Returns `{document_id, message, status: "pending"}`
4. Polling updates the status every 3 seconds
5. On "Upload gagal" shows `alert()` — no user-friendly error UI

### 6.7 Chat Flow

1. Load completed documents + existing chat sessions on mount
2. User selects a document (or none for general chat)
3. User types a message → if no session, create one via `POST /api/chat/sessions`
4. Send message via `POST /api/chat/sessions/:sessionId/messages`
5. Backend proxies to AI Service → returns response
6. Messages displayed in `ChatMessages` component
7. User message shown immediately (optimistic), AI response shown when received

### 6.8 History Flow

1. Load all documents via `GET /api/documents`
2. Filter by status (all/completed/processing/failed) + search by filename
3. Click row → navigate to `/file/:id` detail page
4. Click Delete → `window.confirm()` → `DELETE /api/documents/:id` → remove from state

### 6.9 Security Implications

- **localStorage-based tokens** — vulnerable to XSS (any injected script can read the token)
- **Token not cleared on 401** — no `logout()` call when backend returns 401
- **Chat page bypasses authFetch** — does `localStorage.getItem("auth_token")` manually. Inconsistent but functionally equivalent.
- **No CSRF protection** — cookies not used for auth, but if XSS exists, attacker can read token and make API calls

---

## 7. File Processing & Storage

### 7.1 Upload Validation

**File**: `backend/internal/handlers/uploads.go:36-168`

1. Check authentication (user_id from JWT)
2. Check file exists in multipart form ("file" field)
3. **Extension check**: must end with `.pdf` (case-insensitive)
4. **Magic byte check**: read first 512 bytes → `http.DetectContentType()` → must be `"application/pdf"`
5. **Size check**: must be ≤ 100 MB (`MaxFileSize`)
6. Generate UUID-based filename: `<documentID>.pdf`
7. Save to `UPLOADS_DIR/<documentID>.pdf`
8. Create DB record (status=pending)
9. Create queue item (status=queued)
10. Publish RabbitMQ message with `{document_id, pdf_path, priority}`
11. Return `{document_id, message, status: "pending"}`

### 7.2 File Naming Strategy

- **Uploaded PDF**: `<UUID>.pdf` (renamed from original)
- **Output markdown**: `<UUID>.md`
- **Output JSON**: `<UUID>.json`
- **Extracted images**: `page_<N>_img_<M>.<ext>` or `page_<N>_full.png`
- All stored in respective subdirectories under `uploads/` and `outputs/`

### 7.3 Output Directory Structure

```
uploads/
└── <UUID>.pdf

outputs/
├── markdown/
│   └── <UUID>.md
├── json/
│   └── <UUID>.json
└── images/
    └── <UUID>/
        ├── page_1_img_1.png
        ├── page_1_full.png
        └── ...
```

### 7.4 Image Extraction

**File**: `ai-service/src/extractors/image_extractor.py`

Two modes:
1. **Embedded images**: `page.get_images()` → `doc.extract_image(xref)` — extracts embedded image objects
2. **Page rendering**: `page.get_pixmap(matrix=Matrix(dpi/72))` → saves as PNG — converts page to image (used for scanned PDFs)

### 7.5 Cleanup Flow

- **On delete**: removes uploaded PDF, markdown, JSON, images folder
- **No temp file handling**: the consumer processes in `/app/uploads` directly
- **No orphan cleanup**: if the consumer crashes after saving outputs but before updating status, DB stays in "processing" state forever

---

## 8. Security Audit

### 8.1 Existing Security Mechanisms

| Mechanism | Location | Status |
|-----------|----------|--------|
| JWT authentication | `middleware/auth.go` | ✅ |
| Password hashing (bcrypt) | `handlers/auth.go:57` | ✅ |
| Password min length (8) | `handlers/auth.go:40` | ✅ |
| JWT signing method check | `middleware/auth.go:48` | ✅ |
| Ownership filtering | All DB queries `WHERE user_id = $2` | ✅ (1 gap) |
| CORS whitelist | `middleware/cors.go` | ✅ |
| Rate limiting (auth/chat/upload) | `middleware/ratelimit.go` | ✅ |
| Security headers (CSP, HSTS) | `middleware/security.go` | ✅ |
| File extension + magic byte validation | `handlers/uploads.go` | ✅ |
| Path traversal protection | `handlers/document.go` isPathSafe | ✅ |
| No error leakage | Generic error messages | ✅ |
| Prompt injection filter | `qa_service.py` | ✅ |
| Message length limits | `chat.go:388` + `qa_service.py:50` | ✅ |
| JWT_SECRET required at startup | `config/config.go:65` | ✅ |

### 8.2 Remaining Vulnerabilities

| # | Vulnerability | Severity | Location | Details |
|---|--------------|----------|----------|---------|
| 1 | **XSS via localStorage token** | CRITICAL | `auth.tsx` | Token in localStorage can be stolen by any XSS. CSP allows `unsafe-inline` + `unsafe-eval`. |
| 2 | **No CSRF on chat API** | HIGH | All protected routes | No anti-CSRF token. If user visits attacker site, attacker can't read localStorage but can make requests (if CORS misconfigured). |
| 3 | **No refresh token** | MEDIUM | `auth.go` | 24h token with no refresh means poor UX (force re-login) OR users will extend expiry. |
| 4 | **Unbounded GET endpoints** | MEDIUM | `documents`, `sessions`, `history` | No rate limiting on list endpoints — attacker can hammer these without rate limit checks. |
| 5 | **Race condition on queue ack** | HIGH | `queue_consumer.py:51` | Ack before processing. Crash → lost message. |
| 6 | **No file type limit on images serving** | MEDIUM | `document.go:GetImages` | Returns any file listing from images folder. |
| 7 | **Orphaned "processing" documents** | LOW | `queue_consumer.py` | If AI service crashes during processing, document stays "processing" forever. |
| 8 | **SQL injection potential (Go)** | LOW | `postgres.go` | Parameterized queries used everywhere ($1, $2). Low risk. |
| 9 | **SQL injection potential (Python)** | MEDIUM | `db.py:250` | Uses `$1::uuid` — parameterized, but string concatenation in `_ensure_embedding_column` uses f-string for dimension. |
| 10 | **Logging sensitive data** | LOW | `auth.go:Register` | Error messages might leak email existence (different error for existing vs error). |
| 11 | **No authentication on image URLs** | HIGH | Frontend | Images served via direct `/outputs/images/<id>/<file>` URLs — no JWT check. Anyone who knows the URL can view images. |
| 12 | **No input size limit on upload** | MEDIUM | `uploads.go` | 100MB limit exists but no request body size limit before form parsing. |
| 13 | **No audit logging** | MEDIUM | Everywhere | No record of who deleted which document or accessed which file. |
| 14 | **Chat history without user check** | HIGH | `postgres.go:248` | `GetChatHistory` with empty session ID queries `WHERE document_id = $1` without `user_id` filter. |
| 15 | **Weak CSP** | MEDIUM | `security.go` | `script-src 'unsafe-eval' 'unsafe-inline'` makes CSP largely ineffective against XSS. |

### 8.3 Attack Vectors

1. **Stored XSS**: If a PDF contains JavaScript or malicious text that passes through the pipeline, it could execute in the markdown/JSON viewer
2. **Prompt injection**: Users crafting questions that override the system prompt ("ignore previous instructions...") — partially mitigated by pattern matching
3. **API abuse via queue**: Publishing many messages to RabbitMQ without auth (if exposed)
4. **Large file DoS**: Uploading a 100MB PDF with complex images to exhaust AI service memory
5. **Token replay**: If token is stolen, attacker has 24h access to all documents

---

## 9. Performance Analysis

### 9.1 Bottlenecks

1. **PDF Processing** (CPU + memory heavy):
   - Surya OCR loads large ML models into memory
   - Table Transformer loads two models (detection + structure)
   - All run in a single thread per document
   
2. **Embedding Generation** (I/O + compute):
   - Gemini API call per text chunk (sequential, not batched)
   - Sentence-transformers runs on CPU (no GPU acceleration configured)
   
3. **Database Queries**:
   - `ListDocuments` for every user — no pagination limit exposed to frontend (backend limits to 100, but no `LIMIT` clause in the handler)
   - The polled dashboard page hits `GET /api/documents` every 3 seconds per user
   
4. **Markdown Formatting**:
   - Gemini API call with full document text — blocks processing pipeline

### 9.2 Query Inefficiency

- `save_chunks()` in `db.py` inserts chunks one at a time (not batch insert) — N round-trips for N chunks
- `get_chunks()` has a try-catch for UUID cast — retries whole query on failure
- `GetDocumentStatusCounts` does a `GROUP BY status` without compound index on `(user_id, status)`

### 9.3 Memory Usage

- **Table Transformer**: loads two ~200MB models into RAM
- **Surya OCR**: loads detection + recognition models (~1GB total)
- **Sentence-transformers**: loads all-mpnet-base-v2 (~400MB)
- All models live in memory for the lifetime of the AI service process

### 9.4 Scalability Concerns

- Rate limiter is in-memory (single process only)
- Queue uses `prefetch_count=1` — limits throughput
- No caching layer (no Redis/memcached)
- No read replicas for database
- Image serving bypasses backend auth (direct file URLs)
- File storage is local to the container (not S3/GCS)

### 9.5 Caching Opportunities

- Document status counts could be cached
- Embeddings could be cached per query
- Markdown/JSON outputs are already files — could add CDN
- Chat responses are not cached (every identical question re-queries Gemini)

---

## 10. Deployment & Infrastructure

### 10.1 Docker Architecture

```yaml
# docker-compose.yml
services:
  ai_postgres:    pgvector/pgvector:pg16
  ai_rabbitmq:    rabbitmq:3-management
  ai_backend:     Go binary, exposes 8080
  ai_service:     Python FastAPI, exposes 8000
  ai_frontend:    Next.js, exposes 3000
```

All services share volumes:
```yaml
volumes:
  - ./uploads:/app/uploads
  - ./outputs:/app/outputs
```

### 10.2 Environment Variables

**Required**:
- `POSTGRES_PASSWORD` (must be set, no default)
- `RABBITMQ_PASS` (must be set, no default)
- `JWT_SECRET` (must be set, no default)
- `GEMINI_API_KEY` (must be set in docker-compose)

**Optional with defaults**:
- `POSTGRES_USER=admin`, `POSTGRES_DB=pdf_extractor`
- `RABBITMQ_USER=guest`
- `CORS_ALLOWED_ORIGINS=http://localhost:3000`
- `PORT=8080`, `GIN_MODE=debug`
- `FRONTEND_API_URL=http://localhost:8080`

### 10.3 Production Readiness Gaps

| Gap | Impact |
|-----|--------|
| No health check on frontend service | NGINX/reverse proxy can't detect frontend issues |
| No container CPU/memory limits | Single document can consume all RAM |
| No log aggregation | Logs lost on container restart |
| No metrics/monitoring | Can't detect degradation |
| No backup strategy | Data loss on volume corruption |
| No secrets management | Env vars visible in docker-compose |
| No database migration tool | Multiple separate migration scripts |
| No graceful shutdown handling | Queue messages lost on restart |
| No retry/backoff on queue failures | Failed messages permanently lost |
| Frontend builds at Docker build time | No build cache sharing |

### 10.4 Health Checks

- PostgreSQL: `pg_isready`
- RabbitMQ: `rabbitmq-diagnostics ping`
- Backend: `GET /health` returns `{status: "healthy", service: "PDF Extractor Backend"}`
- AI Service: `GET /health` returns `{status: "healthy", consumer_status: "running"}` and `GET /` returns `{service: "PDF Extractor AI Service", status: "running"}`
- **No health check defined for frontend service in docker-compose**

### 10.5 Failure Recovery

- **PostgreSQL**: Docker restart policy `always` + persistent volume. If corrupted, data is gone.
- **RabbitMQ**: Durable queue, messages are persistent. But ack-before-processing means messages can be lost.
- **Backend**: Stateless, recovers on restart.
- **AI Service**: On restart, consumer starts new daemon thread. No re-queueing of lost messages.
- **Frontend**: Stateless, recovers on restart.

---

## 11. Code Quality Review

### 11.1 Strong Points

- **Clean separation of concerns**: Backend (API gateway) ↔ AI Service (processing) ↔ DB
- **Consistent error response format**: All backend handlers return `{error, message}`
- **Ownership enforced at query level**: `WHERE user_id = $2` on every document/chat operation
- **Graceful fallbacks everywhere**: Gemini → sentence-transformers, transformer tables → pdfplumber, vector search → sequential, Gemini markdown → basic format
- **Lazy model loading**: Table Transformer, Surya OCR, sentence-transformers all load on first use
- **Idempotent migrations**: `CREATE TABLE IF NOT EXISTS`, column existence checks
- **Async DB operations**: Python uses asyncpg with connection pool
- **JWT signing method validation**: Prevents algorithm confusion

### 11.2 Weak Points

- **Duplicated migration logic**: init.sql + Go postgres.go + Python db.py all create tables differently
- **Tight coupling**: Chat handler directly calls AI Service via HTTP — no abstraction layer
- **Mixed sync/async**: Queue consumer uses blocking pika but spawns async event loops in threads
- **No tests whatsoever**: Zero test files across the entire project
- **Error swallowing**: Many `print()` or `logger.error()` without re-raising or returning appropriate errors
- **Inconsistent logging**: Mix of `print()`, `logger.info()`, `fmt.Printf()`, `log.Printf()` across services
- **Hardcoded values**: `all-mpnet-base-v2` in `embedding_service.py`, `gemini-2.5-flash` in `qa_service.py` and `markdown_formatter.py`
- **Type safety gaps**: Python uses `dict` and `List[Dict]` extensively without proper type models

### 11.3 Technical Debt

1. **No `user_id` in `get_chunks` GET endpoint** — the AI service route `GET /api/v1/documents/{id}/chunks` doesn't check ownership
2. **Chat page bypasses authFetch** — inconsistent API calling pattern
3. **`HistoryTable` and `HistoryCard` components exist but are unused** — the history page has inline table code
4. **`process()` function in `pdf_processor.py`** — 70 lines, does too much (detect + extract + images + markdown + save + chunk + embed)
5. **`save_chunks()` inserts one-by-one** — should use batch insert for N chunks
6. **`get_chunks()` UUID cast workaround** — the try-catch for casting suggests schema inconsistency
7. **`extract_tables()` raises NotImplementedError** — dead code

### 11.4 Duplicate Logic

- `init.sql` and `db.py:_ensure_tables()` both create `chat_sessions` and `chat_history` tables
- `formatBytes`, `formatDate`, `STATUS_CONFIG` defined in dashboard, history, AND file detail pages separately
- PDF type detection logic in `pdf_detector.py` and partially in `pdf_processor.py`

### 11.5 Refactor Opportunities

1. **Shared types**: Extract `Doc`, `STATUS_CONFIG`, `formatBytes`, `formatDate` into shared files
2. **Batch DB operations**: Convert `save_chunks()` to use `executemany` or single INSERT with multiple VALUES
3. **API client abstraction**: Single Axios-like wrapper instead of manual `authFetch()` + manual headers
4. **Abstract AI provider**: Interface for embedding + LLM calls to support swapping providers
5. **Middleware cleanup**: Move user_id extraction to a helper function
6. **Async queue consumer**: Replace blocking pika with aio-pika for true async
7. **Null safety in Go models**: Use pointer types consistently for nullable fields

---

## 12. Full Request Lifecycle Diagrams

### 12.1 Upload → Process → Chat (End-to-End)

```
USER                    FRONTEND              BACKEND               AI SERVICE              DB            RABBITMQ
 │                        │                      │                      │                     │               │
 │  Upload PDF            │                      │                      │                     │               │
 │───────────────────────▶│                      │                      │                     │               │
 │                        │ POST /api/upload     │                      │                     │               │
 │                        │─────────────────────▶│                      │                     │               │
 │                        │                      │ Validate file        │                     │               │
 │                        │                      │ Magic bytes check    │                     │               │
 │                        │                      │ Size check           │                     │               │
 │                        │                      │ Save to uploads/     │                     │               │
 │                        │                      │──────────────────────│────────────────────▶│               │
 │                        │                      │ INSERT document      │                     │               │
 │                        │                      │──────────────────────│────────────────────▶│               │
 │                        │                      │ INSERT queue_item    │                     │               │
 │                        │                      │──────────────────────│────────────────────▶│               │
 │                        │                      │ Publish to queue     │                     │               │
 │                        │                      │──────────────────────│────────────────────────────────────▶│
 │                        │  {document_id, msg}  │                      │                     │               │
 │                        │◀─────────────────────│                      │                     │               │
 │  See "pending" status  │                      │                      │                     │               │
 │◀───────────────────────│                      │                      │                     │               │
 │                        │                      │                      │                     │               │
 │  (poll every 3s)       │                      │                      │                     │               │
 │────────────────────────│──────────────────────│                      │                     │               │
 │                        │                      │                      │ Consumer receives    │               │
 │                        │                      │                      │◀────────────────────────────────────│
 │                        │                      │                      │ Update status: proc  │               │
 │                        │                      │                      │─────────────────────▶│               │
 │                        │                      │                      │                      │               │
 │                        │                      │                      │ PDFProcessor.process │               │
 │                        │                      │                      │ ├─ detect_type       │               │
 │                        │                      │                      │ ├─ extract_text      │               │
 │                        │                      │                      │ ├─ extract_tables    │               │
 │                        │                      │                      │ ├─ extract_images    │               │
 │                        │                      │                      │ ├─ generate_markdown │               │
 │                        │                      │                      │ ├─ save_outputs      │               │
 │                        │                      │                      │ ├─ chunk_document    │               │
 │                        │                      │                      │ ├─ generate_embeds   │               │
 │                        │                      │                      │ └─ save_chunks       │               │
 │                        │                      │                      │─────────────────────▶│               │
 │                        │                      │                      │ Update status: done  │               │
 │                        │                      │                      │─────────────────────▶│               │
 │                        │                      │                      │                      │               │
 │  See "completed"       │ GET /api/documents    │                      │                     │               │
 │◀───────────────────────│◀──────────────────────│──────────────────────│────────────────────▶│               │
 │                        │                      │                      │                     │               │
 │  Click "Chat"          │                      │                      │                     │               │
 │────────────────────────│──────────────────────│                      │                     │               │
 │                        │ POST /api/chat/sessions/:id/messages        │                     │               │
 │                        │─────────────────────▶│                      │                     │               │
 │                        │                      │ Save user msg        │                     │               │
 │                        │                      │──────────────────────│────────────────────▶│               │
 │                        │                      │ POST /api/v1/chat    │                     │               │
 │                        │                      │─────────────────────▶│                     │               │
 │                        │                      │                      │ Sanitize input       │               │
 │                        │                      │                      │ Injection check      │               │
 │                        │                      │                      │ Generate query emb   │               │
 │                        │                      │                      │ Vector search        │               │
 │                        │                      │                      │─────────────────────▶│               │
 │                        │                      │                      │ Build prompt + GenAI │               │
 │                        │                      │                      │ Return response      │               │
 │                        │                      │◀─────────────────────│                      │               │
 │                        │                      │ Save assistant msg   │                     │               │
 │                        │                      │──────────────────────│────────────────────▶│               │
 │                        │  ChatResponse        │                      │                     │               │
 │                        │◀─────────────────────│                      │                     │               │
 │  See AI response       │                      │                      │                     │               │
 │◀───────────────────────│                      │                      │                     │               │
```

### 12.2 What Happens Internally When User Asks a Question

1. **Frontend**: `sendMessage()` in `chat/page.tsx:181`
   - Creates optimistic user message object
   - Appends to local `messages` state
   - If no `currentSessionId`, creates session via `POST /api/chat/sessions`
   - Calls backend: `POST /api/chat/sessions/:sessionId/messages`

2. **Backend** (`chat.go:215-296`):
   - Validates JWT → gets `user_id`
   - Loads session from DB (verifies ownership)
   - Saves user message to `chat_history`
   - Calls `callAIService()` → HTTP POST to AI Service `/api/v1/chat`

3. **AI Service** (`qa_service.py:145-195`):
   - Sanitizes input (4000 char limit, strip system tokens)
   - Checks injection patterns
   - Calls `_retrieve_relevant_chunks(document_id, question)`:
     - Calls `generate_query_embedding(question)` → embedding (768d float list)
     - Calls `search_similar_chunks(document_id, query_embedding, top_k=5, min_similarity=0.5)`
     - SQL: `SELECT ... 1 - (embedding <=> $2::vector) AS similarity ... ORDER BY embedding <=> $2::vector LIMIT 5`
     - If fails: falls back to `get_chunks(document_id)` → first 5 sequential chunks
     - Builds context string with relevance scores
   - Constructs prompt: `"Answer based ONLY on provided context. CONTEXT: {chunks} QUESTION: {question}"`
   - Calls `genai.GenerativeModel("gemini-2.5-flash").generate_content(prompt)`
   - Returns response text

4. **Backend**: saves assistant message + returns to frontend

5. **Frontend**: appends AI response to messages list

---

## 13. Critical Security Observations

### 13.1 localStorage Token Storage

The most critical security concern. Any XSS vulnerability anywhere in the application allows an attacker to:

```javascript
localStorage.getItem("auth_token")  // → steal JWT
localStorage.getItem("auth_user")   // → steal user info
fetch("/api/documents", { headers: { Authorization: `Bearer ${token}` } })
// → exfiltrate all documents
```

**Mitigated by**: CSP headers (but weakened by `unsafe-inline` + `unsafe-eval`)

### 13.2 No Rate Limiting on List Endpoints

`GET /api/documents`, `GET /api/chat/sessions`, `GET /api/documents/:id/markdown` have no rate limits. An attacker can:
- Enumerate all documents by user ID
- Repeatedly download large markdown/JSON files (bandwidth DoS)
- Hammer the database with list queries

### 13.3 Queue Message Loss on Crash

In `queue_consumer.py:51`:
```python
ch.basic_ack(delivery_tag=method.delivery_tag)  # Ack before processing
thread = threading.Thread(target=self.run_thread, args=(msg,))
thread.start()
```

If the container crashes between the ack and the DB status update, the message is gone permanently. No redelivery, no retry queue, no dead letter exchange.

### 13.4 No Authentication on Image URLs

Images are served directly via:
```
http://backend:8080/outputs/images/<docId>/<filename>
```

Anyone who knows the URL pattern can view any document's images. The backend's `ServeOutput` handler has path traversal protection but no authentication check on the images route (the frontend constructs URLs directly to the image path).

### 13.5 Chat History Without User Filter

In certain query paths (`postgres.go:248`):
```go
WHERE document_id = $1  // No user_id filter!
```

This is in `GetChatHistory` when `sessionID` is empty. An authenticated user could read any document's chat history by guessing document IDs.

---

## 14. Top 10 Technical Risks

| # | Risk | Severity | Impact | Mitigation |
|---|------|----------|--------|------------|
| 1 | **Queue message loss** | CRITICAL | Documents stuck in "processing" forever | Move ack after processing completes. Add dead letter queue. |
| 2 | **XSS via CSP bypass** | CRITICAL | Account takeover via token theft | Tighten CSP (remove `unsafe-inline` `unsafe-eval`). Switch to httpOnly cookies. |
| 3 | **No database migration tool** | HIGH | Schema divergence between init.sql, Go, and Python | Use a single migration tool (e.g., goose, alembic). |
| 4 | **Embedding pipeline fragility** | HIGH | All chunks saved without embeddings (silent failure) | Add alerting on NULL embedding counts. |
| 5 | **OOM from large PDFs** | HIGH | AI service crashes on complex documents | Set Docker memory limits. Add document page count check. |
| 6 | **No chat ownership on history** | HIGH | Cross-user chat history exposure | Add `user_id` filter to all GetChatHistory query paths. |
| 7 | **No backup/DR strategy** | HIGH | Complete data loss on volume failure | Add automated backups to S3. Document recovery procedure. |
| 8 | **Orphaned processing documents** | MEDIUM | Documents stuck in "processing" state | Add periodic cleanup job to reset stuck items. |
| 9 | **Rate limiter single-instance** | MEDIUM | Ineffective behind load balancer | Switch to Redis-based distributed rate limiter. |
| 10 | **No test coverage** | MEDIUM | Regression safety net missing | Add integration tests for upload → process → chat flow. |

---

## 15. Top 10 Improvement Priorities

| # | Priority | Effort | Impact | Description |
|---|----------|--------|--------|-------------|
| 1 | **Fix queue ack ordering** | 1 day | CRITICAL | Move `basic_ack` after successful processing. Add dead letter queue for retries. |
| 2 | **Switch to httpOnly cookies** | 2 days | CRITICAL | Replace localStorage token with secure, httpOnly, SameSite cookies. Eliminates XSS token theft. |
| 3 | **Add user_id to all chat queries** | 0.5 day | HIGH | Fix `GetChatHistory` sessionless branch to filter by `user_id`. |
| 4 | **Tighten CSP** | 0.5 day | HIGH | Remove `unsafe-inline` and `unsafe-eval` from script-src. Use nonces or hashes. |
| 5 | **Add database migration tool** | 2 days | HIGH | Consolidate all schema changes into a single tool (goose for Go, alembic for Python). |
| 6 | **Add authentication to image URLs** | 1 day | HIGH | Serve images through authenticated handler instead of direct file URLs. |
| 7 | **Add rate limiting to all endpoints** | 1 day | MEDIUM | Apply rate limiter to GET endpoints, not just POST. |
| 8 | **Add batch insert for chunks** | 0.5 day | MEDIUM | Convert `save_chunks()` to use `asyncpg.executemany()` or single multi-VALUES insert. |
| 9 | **Add container resource limits** | 0.5 day | MEDIUM | Set `deploy.resources.limits` in docker-compose for all services. |
| 10 | **Add unit + integration tests** | 1 week | MEDIUM | Cover upload, processing, chunking, embedding, vector search, and chat flows. |
