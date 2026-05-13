package handlers

import (
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/ahmadhasanm/ai-document-extractor/internal/config"
	"github.com/ahmadhasanm/ai-document-extractor/internal/database"
	"github.com/ahmadhasanm/ai-document-extractor/internal/models"
	"github.com/ahmadhasanm/ai-document-extractor/internal/queue"
)

type UploadHandler struct {
	db       *database.Database
	queue    *queue.RabbitMQ
	config   *config.Config
}

func NewUploadHandler(db *database.Database, q *queue.RabbitMQ, cfg *config.Config) *UploadHandler {
	// Ensure uploads directory exists
	os.MkdirAll(cfg.UploadsDir, 0755)
	
	return &UploadHandler{
		db:     db,
		queue:  q,
		config: cfg,
	}
}

func (h *UploadHandler) Upload(c *gin.Context) {
	// Parse multipart form
	file, header, err := c.Request.FormFile("file")
	if err != nil {
		c.JSON(http.StatusBadRequest, models.ErrorResponse{
			Error:   "bad_request",
			Message: "No file uploaded",
		})
		return
	}
	defer file.Close()

	// Validate file type
	if filepath.Ext(header.Filename) != ".pdf" {
		c.JSON(http.StatusBadRequest, models.ErrorResponse{
			Error:   "invalid_file_type",
			Message: "Only PDF files are allowed",
		})
		return
	}

	// Validate file size
	if header.Size > h.config.MaxFileSize {
		c.JSON(http.StatusBadRequest, models.ErrorResponse{
			Error:   "file_too_large",
			Message: fmt.Sprintf("File size exceeds maximum of %d MB", h.config.MaxFileSize/(1024*1024)),
		})
		return
	}

	// Generate unique ID and filename
	documentID := uuid.New().String()
	filename := fmt.Sprintf("%s.pdf", documentID)
	filePath := filepath.Join(h.config.UploadsDir, filename)

	// Save file to disk
	dst, err := os.Create(filePath)
	if err != nil {
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error:   "internal_error",
			Message: "Failed to save file",
		})
		return
	}
	defer dst.Close()

	if _, err := io.Copy(dst, file); err != nil {
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error:   "internal_error",
			Message: "Failed to save file",
		})
		return
	}

	// Create document record
	doc := &models.Document{
		ID:               documentID,
		Filename:         filename,
		OriginalFilename: header.Filename,
		FilePath:         filePath,
		FileSize:         header.Size,
		Status:           "pending",
	}

	if err := h.db.CreateDocument(doc); err != nil {
		// Cleanup file
		os.Remove(filePath)
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error:   "database_error",
			Message: "Failed to create document record",
		})
		return
	}

	// Create queue item
	queueItem := &models.ProcessingQueue{
		ID:         uuid.New().String(),
		DocumentID: documentID,
		Priority:   0,
		Status:     "queued",
	}

	if err := h.db.CreateQueueItem(queueItem); err != nil {
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error:   "database_error",
			Message: "Failed to create queue item",
		})
		return
	}

	// Publish to RabbitMQ
	queueMsg := &models.QueueMessage{
		DocumentID: documentID,
		PDFPath:    filePath,
		Priority:   0,
	}

	if err := h.queue.PublishMessage(queueMsg); err != nil {
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error:   "queue_error",
			Message: "Failed to queue document for processing",
		})
		return
	}

	// Return success response
	c.JSON(http.StatusOK, models.UploadResponse{
		DocumentID: documentID,
		Message:    "Document uploaded successfully and queued for processing",
		Status:     "pending",
	})
}