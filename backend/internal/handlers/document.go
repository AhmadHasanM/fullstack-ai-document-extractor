package handlers

import (
	"net/http"
	"os"

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
	documents, err := h.db.ListDocuments(100, 0)
	if err != nil {
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error:   "database_error",
			Message: err.Error(),
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"documents": documents,
	})
}

func (h *DocumentHandler) Get(c *gin.Context) {
	id := c.Param("id")

	doc, err := h.db.GetDocument(id)
	if err != nil {
		c.JSON(http.StatusNotFound, models.ErrorResponse{
			Error:   "not_found",
			Message: err.Error(),
		})
		return
	}

	c.JSON(http.StatusOK, doc)
}

func (h *DocumentHandler) Delete(c *gin.Context) {
	id := c.Param("id")

	doc, err := h.db.GetDocument(id)
	if err != nil {
		c.JSON(http.StatusNotFound, models.ErrorResponse{
			Error:   "not_found",
			Message: err.Error(),
		})
		return
	}

	// delete uploaded file
	os.Remove(doc.FilePath)

	// delete db record
	if err := h.db.DeleteDocument(id); err != nil {
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error:   "database_error",
			Message: err.Error(),
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message": "document deleted",
	})
}

func (h *DocumentHandler) GetMarkdown(c *gin.Context) {
	id := c.Param("id")

	output, err := h.db.GetDocumentOutput(id)
	if err != nil {
		c.JSON(http.StatusNotFound, models.ErrorResponse{
			Error:   "not_found",
			Message: err.Error(),
		})
		return
	}

	c.File(output.MarkdownPath)
}

func (h *DocumentHandler) GetJSON(c *gin.Context) {
	id := c.Param("id")

	output, err := h.db.GetDocumentOutput(id)
	if err != nil {
		c.JSON(http.StatusNotFound, models.ErrorResponse{
			Error:   "not_found",
			Message: err.Error(),
		})
		return
	}

	c.File(output.JSONPath)
}

func (h *DocumentHandler) GetImages(c *gin.Context) {
	id := c.Param("id")

	output, err := h.db.GetDocumentOutput(id)
	if err != nil {
		c.JSON(http.StatusNotFound, models.ErrorResponse{
			Error:   "not_found",
			Message: err.Error(),
		})
		return
	}

	files, err := os.ReadDir(output.ImagesFolder)
	if err != nil {
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error:   "filesystem_error",
			Message: err.Error(),
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