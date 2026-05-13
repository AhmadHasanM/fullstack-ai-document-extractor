package models

import "time"

type Document struct {
	ID               string     `json:"id"`
	Filename         string     `json:"filename"`
	OriginalFilename string     `json:"original_filename"`
	FilePath         string     `json:"file_path"`
	FileSize         int64      `json:"file_size"`
	PDFType          *string    `json:"pdf_type,omitempty"`
	Status           string     `json:"status"`
	ErrorMessage     *string    `json:"error_message,omitempty"`
	CreatedAt        time.Time  `json:"created_at"`
	UpdatedAt        time.Time  `json:"updated_at"`
	ProcessedAt      *time.Time `json:"processed_at,omitempty"`
}

type DocumentOutput struct {
	ID            string    `json:"id"`
	DocumentID    string    `json:"document_id"`
	MarkdownPath  string    `json:"markdown_path"`
	JSONPath      string    `json:"json_path"`
	ImagesFolder  string    `json:"images_folder"`
	CreatedAt     time.Time `json:"created_at"`
}

type DocumentChunk struct {
	ID         string                 `json:"id"`
	DocumentID string                 `json:"document_id"`
	ChunkIndex int                    `json:"chunk_index"`
	Content    string                 `json:"content"`
	PageNumber *int                   `json:"page_number,omitempty"`
	ChunkType  string                 `json:"chunk_type"`
	Metadata   map[string]interface{} `json:"metadata,omitempty"`
	CreatedAt  time.Time              `json:"created_at"`
}

type ProcessingQueue struct {
	ID            string     `json:"id"`
	DocumentID    string     `json:"document_id"`
	Priority      int        `json:"priority"`
	Status        string     `json:"status"`
	RetryCount    int        `json:"retry_count"`
	MaxRetries    int        `json:"max_retries"`
	ErrorMessage  *string    `json:"error_message,omitempty"`
	CreatedAt     time.Time  `json:"created_at"`
	StartedAt     *time.Time `json:"started_at,omitempty"`
	CompletedAt   *time.Time `json:"completed_at,omitempty"`
}

type ChatMessage struct {
	ID         string    `json:"id"`
	DocumentID string    `json:"document_id"`
	SessionID  string    `json:"session_id"`
	Role       string    `json:"role"`
	Message    string    `json:"message"`
	CreatedAt  time.Time `json:"created_at"`
}

type UploadRequest struct {
	File []byte `json:"file"`
}

type UploadResponse struct {
	DocumentID string `json:"document_id"`
	Message    string `json:"message"`
	Status     string `json:"status"`
}

type ChatRequest struct {
	Message   string `json:"message" binding:"required"`
	SessionID string `json:"session_id" binding:"required"`
}

type ChatResponse struct {
	Response  string    `json:"response"`
	SessionID string    `json:"session_id"`
	Timestamp time.Time `json:"timestamp"`
}

type QueueMessage struct {
	DocumentID string `json:"document_id"`
	PDFPath    string `json:"pdf_path"`
	Priority   int    `json:"priority"`
}

type ErrorResponse struct {
	Error   string `json:"error"`
	Message string `json:"message"`
}