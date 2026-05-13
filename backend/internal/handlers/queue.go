package handlers

import (
	"net/http"

	"github.com/ahmadhasanm/ai-document-extractor/internal/database"
	"github.com/ahmadhasanm/ai-document-extractor/internal/models"
	"github.com/gin-gonic/gin"
)

type QueueHandler struct {
	db *database.Database
}

func NewQueueHandler(db *database.Database) *QueueHandler {
	return &QueueHandler{
		db: db,
	}
}

func (h *QueueHandler) GetStatus(c *gin.Context) {
	counts, err := h.db.GetDocumentStatusCounts()
	if err != nil {
		c.JSON(http.StatusOK, gin.H{
			"status":     "queue active",
			"pending":    0,
			"processing": 0,
			"completed":  0,
			"failed":     0,
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"status":     "queue active",
		"pending":    counts["pending"],
		"processing": counts["processing"],
		"completed":  counts["completed"],
		"failed":     counts["failed"],
	})
}

func (h *QueueHandler) GetDocumentStatus(c *gin.Context) {
	id := c.Param("id")

	queueItem, err := h.db.GetQueueStatus(id)
	if err != nil {
		c.JSON(http.StatusNotFound, models.ErrorResponse{
			Error:   "not_found",
			Message: err.Error(),
		})
		return
	}

	c.JSON(http.StatusOK, queueItem)
}