package handlers

import (
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"strings"

	"github.com/gin-gonic/gin"

	"github.com/ahmadhasanm/ai-document-extractor/internal/config"
	"github.com/ahmadhasanm/ai-document-extractor/internal/database"
	"github.com/ahmadhasanm/ai-document-extractor/internal/models"
	"github.com/ahmadhasanm/ai-document-extractor/internal/queue"
)

type DocumentHandler struct {
	db     *database.Database
	queue  *queue.RabbitMQ
	config *config.Config
}

func NewDocumentHandler(
	db *database.Database,
	q *queue.RabbitMQ,
	cfg *config.Config,
) *DocumentHandler {
	return &DocumentHandler{
		db:     db,
		queue:  q,
		config: cfg,
	}
}

func (h *DocumentHandler) List(c *gin.Context) {
	userID := c.GetString("user_id")
	if userID == "" {
		c.JSON(http.StatusUnauthorized, models.ErrorResponse{
			Error:   "unauthorized",
			Message: "Not authenticated",
		})
		return
	}

	documents, err := h.db.ListDocuments(userID, 100, 0)
	if err != nil {
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error:   "server_error",
			Message: "Failed to fetch documents",
		})
		return
	}

	if documents == nil {
		documents = []models.Document{}
	}

	c.JSON(http.StatusOK, gin.H{
		"documents": documents,
	})
}

func (h *DocumentHandler) Get(c *gin.Context) {
	id := c.Param("id")
	userID := c.GetString("user_id")
	if userID == "" {
		c.JSON(http.StatusUnauthorized, models.ErrorResponse{
			Error:   "unauthorized",
			Message: "Not authenticated",
		})
		return
	}

	doc, err := h.db.GetDocument(id, userID)
	if err != nil {
		c.JSON(http.StatusNotFound, models.ErrorResponse{
			Error:   "not_found",
			Message: "Document not found",
		})
		return
	}

	c.JSON(http.StatusOK, doc)
}

func (h *DocumentHandler) Delete(c *gin.Context) {
	id := c.Param("id")
	userID := c.GetString("user_id")
	if userID == "" {
		c.JSON(http.StatusUnauthorized, models.ErrorResponse{
			Error:   "unauthorized",
			Message: "Not authenticated",
		})
		return
	}

	doc, err := h.db.GetDocument(id, userID)
	if err != nil {
		c.JSON(http.StatusNotFound, models.ErrorResponse{
			Error:   "not_found",
			Message: "Document not found",
		})
		return
	}

	// Remove uploaded PDF file
	os.Remove(doc.FilePath)

	// Remove output files (markdown, JSON, images) if they exist
	output, err := h.db.GetDocumentOutput(id)
	if err == nil && output != nil {
		if output.MarkdownPath != "" {
			os.Remove(output.MarkdownPath)
		}
		if output.JSONPath != "" {
			os.Remove(output.JSONPath)
		}
		if output.ImagesFolder != "" {
			os.RemoveAll(output.ImagesFolder)
		}
	}

	// Delete related chat sessions (SET NULL on document_id means sessions aren't auto-deleted)
	if err := h.db.DeleteDocumentChatSessions(id, userID); err != nil {
		fmt.Printf("Warning: failed to delete chat sessions for document %s: %v\n", id, err)
	}

	// Delete document from DB (cascades to chunks, outputs, extracted_elements, processing_queue, chat_history)
	if err := h.db.DeleteDocument(id, userID); err != nil {
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error:   "server_error",
			Message: "Failed to delete document",
		})
		return
	}

	c.JSON(http.StatusOK, models.SuccessResponse{
		Message: "Document deleted successfully",
	})
}

func (h *DocumentHandler) GetMarkdown(c *gin.Context) {
	id := c.Param("id")
	userID := c.GetString("user_id")

	doc, err := h.db.GetDocument(id, userID)
	if err != nil {
		c.JSON(http.StatusNotFound, models.ErrorResponse{
			Error:   "not_found",
			Message: "Document not found",
		})
		return
	}

	output, err := h.db.GetDocumentOutput(doc.ID)
	if err != nil {
		c.JSON(http.StatusNotFound, models.ErrorResponse{
			Error:   "not_found",
			Message: "Output not found",
		})
		return
	}

	if !h.isPathSafe(output.MarkdownPath) {
		c.JSON(http.StatusForbidden, models.ErrorResponse{
			Error:   "forbidden",
			Message: "Access denied",
		})
		return
	}

	c.File(output.MarkdownPath)
}

func (h *DocumentHandler) GetJSON(c *gin.Context) {
	id := c.Param("id")
	userID := c.GetString("user_id")

	doc, err := h.db.GetDocument(id, userID)
	if err != nil {
		c.JSON(http.StatusNotFound, models.ErrorResponse{
			Error:   "not_found",
			Message: "Document not found",
		})
		return
	}

	output, err := h.db.GetDocumentOutput(doc.ID)
	if err != nil {
		c.JSON(http.StatusNotFound, models.ErrorResponse{
			Error:   "not_found",
			Message: "Output not found",
		})
		return
	}

	if !h.isPathSafe(output.JSONPath) {
		c.JSON(http.StatusForbidden, models.ErrorResponse{
			Error:   "forbidden",
			Message: "Access denied",
		})
		return
	}

	c.File(output.JSONPath)
}

func (h *DocumentHandler) GetImages(c *gin.Context) {
	id := c.Param("id")
	userID := c.GetString("user_id")

	doc, err := h.db.GetDocument(id, userID)
	if err != nil {
		c.JSON(http.StatusNotFound, models.ErrorResponse{
			Error:   "not_found",
			Message: "Document not found",
		})
		return
	}

	output, err := h.db.GetDocumentOutput(doc.ID)
	if err != nil {
		c.JSON(http.StatusNotFound, models.ErrorResponse{
			Error:   "not_found",
			Message: "Output not found",
		})
		return
	}

	if !h.isPathSafe(output.ImagesFolder) {
		c.JSON(http.StatusForbidden, models.ErrorResponse{
			Error:   "forbidden",
			Message: "Access denied",
		})
		return
	}

	files, err := os.ReadDir(output.ImagesFolder)
	if err != nil {
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error:   "server_error",
			Message: "Failed to read images",
		})
		return
	}

	var images []string
	for _, file := range files {
		images = append(images, file.Name())
	}

	c.JSON(http.StatusOK, gin.H{
		"images": images,
	})
}

func (h *DocumentHandler) ServeOutput(c *gin.Context) {
	userID := c.GetString("user_id")
	if userID == "" {
		c.AbortWithStatusJSON(http.StatusUnauthorized, models.ErrorResponse{
			Error:   "unauthorized",
			Message: "Authentication required",
		})
		return
	}

	reqPath := c.Param("filepath")
	if !h.isPathSafe(reqPath) {
		c.AbortWithStatusJSON(http.StatusForbidden, models.ErrorResponse{
			Error:   "forbidden",
			Message: "Access denied",
		})
		return
	}

	fullPath := filepath.Join(h.config.OutputsDir, reqPath)
	if _, err := os.Stat(fullPath); os.IsNotExist(err) {
		c.AbortWithStatusJSON(http.StatusNotFound, models.ErrorResponse{
			Error:   "not_found",
			Message: "File not found",
		})
		return
	}

	c.File(fullPath)
}

func (h *DocumentHandler) isPathSafe(path string) bool {
	clean := filepath.Clean(path)
	return !strings.Contains(clean, "..")
}
