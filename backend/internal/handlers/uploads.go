package handlers

import (
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"

	"github.com/ahmadhasanm/ai-document-extractor/internal/config"
	"github.com/ahmadhasanm/ai-document-extractor/internal/database"
	"github.com/ahmadhasanm/ai-document-extractor/internal/models"
	"github.com/ahmadhasanm/ai-document-extractor/internal/queue"
)

type UploadHandler struct {
	db     *database.Database
	queue  *queue.RabbitMQ
	config *config.Config
}

func NewUploadHandler(db *database.Database, q *queue.RabbitMQ, cfg *config.Config) *UploadHandler {
	os.MkdirAll(cfg.UploadsDir, 0755)

	return &UploadHandler{
		db:     db,
		queue:  q,
		config: cfg,
	}
}

func (h *UploadHandler) Upload(c *gin.Context) {
	userID := c.GetString("user_id")
	if userID == "" {
		c.JSON(http.StatusUnauthorized, models.ErrorResponse{
			Error:   "unauthorized",
			Message: "Not authenticated",
		})
		return
	}

	file, header, err := c.Request.FormFile("file")
	if err != nil {
		c.JSON(http.StatusBadRequest, models.ErrorResponse{
			Error:   "bad_request",
			Message: "No file uploaded",
		})
		return
	}
	defer file.Close()

	ext := strings.ToLower(filepath.Ext(header.Filename))
	if ext != ".pdf" {
		c.JSON(http.StatusBadRequest, models.ErrorResponse{
			Error:   "invalid_file_type",
			Message: "Only PDF files are allowed",
		})
		return
	}

	buffer := make([]byte, 512)
	if _, err := file.Read(buffer); err != nil {
		c.JSON(http.StatusBadRequest, models.ErrorResponse{
			Error:   "bad_request",
			Message: "Failed to read file",
		})
		return
	}
	file.Seek(0, io.SeekStart)

	contentType := http.DetectContentType(buffer)
	if contentType != "application/pdf" {
		c.JSON(http.StatusBadRequest, models.ErrorResponse{
			Error:   "invalid_file_type",
			Message: "File is not a valid PDF",
		})
		return
	}

	if header.Size > h.config.MaxFileSize {
		c.JSON(http.StatusBadRequest, models.ErrorResponse{
			Error:   "file_too_large",
			Message: fmt.Sprintf("File size exceeds maximum of %d MB", h.config.MaxFileSize/(1024*1024)),
		})
		return
	}

	documentID := uuid.New().String()
	filename := fmt.Sprintf("%s.pdf", documentID)
	filePath := filepath.Join(h.config.UploadsDir, filename)

	dst, err := os.Create(filePath)
	if err != nil {
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error:   "server_error",
			Message: "Failed to save file",
		})
		return
	}
	defer dst.Close()

	if _, err := io.Copy(dst, file); err != nil {
		os.Remove(filePath)
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error:   "server_error",
			Message: "Failed to save file",
		})
		return
	}

	doc := &models.Document{
		ID:               documentID,
		UserID:           userID,
		Filename:         filename,
		OriginalFilename: header.Filename,
		FilePath:         filePath,
		FileSize:         header.Size,
		Status:           "pending",
	}

	if err := h.db.CreateDocument(doc); err != nil {
		os.Remove(filePath)
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error:   "server_error",
			Message: "Failed to create document record",
		})
		return
	}

	queueItem := &models.ProcessingQueue{
		ID:         uuid.New().String(),
		DocumentID: documentID,
		Priority:   0,
		Status:     "queued",
	}

	if err := h.db.CreateQueueItem(queueItem); err != nil {
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error:   "server_error",
			Message: "Failed to queue document",
		})
		return
	}

	queueMsg := &models.QueueMessage{
		DocumentID: documentID,
		PDFPath:    filePath,
		Priority:   0,
	}

	if err := h.queue.PublishMessage(queueMsg); err != nil {
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error:   "server_error",
			Message: "Failed to queue document for processing",
		})
		return
	}

	c.JSON(http.StatusOK, models.UploadResponse{
		DocumentID: documentID,
		Message:    "Document uploaded successfully and queued for processing",
		Status:     "pending",
	})
}
