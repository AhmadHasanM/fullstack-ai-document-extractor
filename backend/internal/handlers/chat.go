package handlers

import (
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"

	"github.com/ahmadhasanm/ai-document-extractor/internal/config"
	"github.com/ahmadhasanm/ai-document-extractor/internal/database"
	"github.com/ahmadhasanm/ai-document-extractor/internal/models"
)

type ChatHandler struct {
	db     *database.Database
	config *config.Config
}

func NewChatHandler(
	db *database.Database,
	cfg *config.Config,
) *ChatHandler {
	return &ChatHandler{
		db:     db,
		config: cfg,
	}
}

func (h *ChatHandler) Chat(c *gin.Context) {
	documentID := c.Param("id")

	var req models.ChatRequest

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, models.ErrorResponse{
			Error:   "bad_request",
			Message: err.Error(),
		})
		return
	}

	userMessage := &models.ChatMessage{
		ID:         uuid.New().String(),
		DocumentID: documentID,
		SessionID:  req.SessionID,
		Role:       "user",
		Message:    req.Message,
	}

	h.db.SaveChatMessage(userMessage)

	// dummy AI response
	aiResponse := "AI response will be implemented later using RAG."

	assistantMessage := &models.ChatMessage{
		ID:         uuid.New().String(),
		DocumentID: documentID,
		SessionID:  req.SessionID,
		Role:       "assistant",
		Message:    aiResponse,
	}

	h.db.SaveChatMessage(assistantMessage)

	c.JSON(http.StatusOK, models.ChatResponse{
		Response:  aiResponse,
		SessionID: req.SessionID,
		Timestamp: time.Now(),
	})
}

func (h *ChatHandler) GetHistory(c *gin.Context) {
	documentID := c.Param("id")
	sessionID := c.Query("session_id")

	history, err := h.db.GetChatHistory(documentID, sessionID, 50)
	if err != nil {
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error:   "database_error",
			Message: err.Error(),
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"history": history,
	})
}