package handlers

import (
	"bytes"
	"encoding/json"
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

func (h *ChatHandler) CreateChatSession(c *gin.Context) {
	userID := c.GetString("user_id")
	if userID == "" {
		c.JSON(http.StatusUnauthorized, models.ErrorResponse{
			Error:   "unauthorized",
			Message: "Not authenticated",
		})
		return
	}

	var req models.CreateChatSessionRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, models.ErrorResponse{
			Error:   "bad_request",
			Message: "Invalid request",
		})
		return
	}

	if req.Title == "" {
		req.Title = "New Chat"
	}

	session := &models.ChatSession{
		ID:         uuid.New().String(),
		UserID:     userID,
		DocumentID: req.DocumentID,
		Title:      req.Title,
	}

	if err := h.db.CreateChatSession(session); err != nil {
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error:   "server_error",
			Message: "Failed to create session",
		})
		return
	}

	c.JSON(http.StatusCreated, models.CreateChatSessionResponse{
		SessionID: session.ID,
		Title:     session.Title,
		CreatedAt: session.CreatedAt,
	})
}

func (h *ChatHandler) ListChatSessions(c *gin.Context) {
	userID := c.GetString("user_id")
	if userID == "" {
		c.JSON(http.StatusUnauthorized, models.ErrorResponse{
			Error:   "unauthorized",
			Message: "Not authenticated",
		})
		return
	}

	sessions, err := h.db.ListChatSessions(userID, 50, 0)
	if err != nil {
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error:   "server_error",
			Message: "Failed to fetch sessions",
		})
		return
	}

	if sessions == nil {
		sessions = []models.ChatSession{}
	}

	c.JSON(http.StatusOK, models.ListChatSessionsResponse{
		Sessions: sessions,
	})
}

func (h *ChatHandler) GetChatSession(c *gin.Context) {
	userID := c.GetString("user_id")
	sessionID := c.Param("id")

	session, err := h.db.GetChatSession(sessionID, userID)
	if err != nil {
		c.JSON(http.StatusNotFound, models.ErrorResponse{
			Error:   "not_found",
			Message: "Chat session not found",
		})
		return
	}

	c.JSON(http.StatusOK, session)
}

func (h *ChatHandler) DeleteChatSession(c *gin.Context) {
	userID := c.GetString("user_id")
	sessionID := c.Param("id")

	if sessionID == "" {
		c.JSON(http.StatusBadRequest, models.ErrorResponse{
			Error:   "bad_request",
			Message: "Session ID required",
		})
		return
	}

	if err := h.db.DeleteChatSession(sessionID, userID); err != nil {
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error:   "server_error",
			Message: "Failed to delete session",
		})
		return
	}

	c.JSON(http.StatusOK, models.SuccessResponse{
		Message: "Chat session deleted",
	})
}

func (h *ChatHandler) Chat(c *gin.Context) {
	userID := c.GetString("user_id")
	if userID == "" {
		c.JSON(http.StatusUnauthorized, models.ErrorResponse{
			Error:   "unauthorized",
			Message: "Not authenticated",
		})
		return
	}

	documentID := c.Param("id")

	var req models.ChatRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, models.ErrorResponse{
			Error:   "bad_request",
			Message: "Invalid request",
		})
		return
	}

	safeMessage := sanitizeMessage(req.Message)

	userMessage := &models.ChatMessage{
		ID:         uuid.New().String(),
		UserID:     userID,
		DocumentID: documentID,
		SessionID:  req.SessionID,
		Role:       "user",
		Message:    safeMessage,
	}

	if err := h.db.SaveChatMessage(userMessage); err != nil {
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error:   "server_error",
			Message: "Failed to save message",
		})
		return
	}

	aiResponse, err := h.callAIService(documentID, req.SessionID, safeMessage)
	if err != nil {
		aiResponse = "I apologize, but I'm having trouble processing your request right now. Please try again later."
	}

	assistantMessage := &models.ChatMessage{
		ID:         uuid.New().String(),
		UserID:     userID,
		DocumentID: documentID,
		SessionID:  req.SessionID,
		Role:       "assistant",
		Message:    aiResponse,
	}

	if err := h.db.SaveChatMessage(assistantMessage); err != nil {
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error:   "server_error",
			Message: "Failed to save response",
		})
		return
	}

	c.JSON(http.StatusOK, models.ChatResponse{
		Response:  aiResponse,
		SessionID: req.SessionID,
		Timestamp: time.Now(),
	})
}

func (h *ChatHandler) ChatWithSession(c *gin.Context) {
	userID := c.GetString("user_id")
	if userID == "" {
		c.JSON(http.StatusUnauthorized, models.ErrorResponse{
			Error:   "unauthorized",
			Message: "Not authenticated",
		})
		return
	}

	sessionID := c.Param("sessionId")

	var req models.ChatRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, models.ErrorResponse{
			Error:   "bad_request",
			Message: "Invalid request",
		})
		return
	}

	session, err := h.db.GetChatSession(sessionID, userID)
	if err != nil {
		c.JSON(http.StatusNotFound, models.ErrorResponse{
			Error:   "not_found",
			Message: "Chat session not found",
		})
		return
	}

	documentID := req.DocumentID
	if documentID == "" && session.DocumentID != nil {
		documentID = *session.DocumentID
	}

	safeMessage := sanitizeMessage(req.Message)

	userMessage := &models.ChatMessage{
		ID:         uuid.New().String(),
		UserID:     userID,
		DocumentID: documentID,
		SessionID:  sessionID,
		Role:       "user",
		Message:    safeMessage,
	}

	if err := h.db.SaveChatMessage(userMessage); err != nil {
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error:   "server_error",
			Message: "Failed to save message",
		})
		return
	}

	aiResponse, err := h.callAIService(documentID, sessionID, safeMessage)
	if err != nil {
		aiResponse = "I apologize, but I'm having trouble processing your request right now. Please try again later."
	}

	assistantMessage := &models.ChatMessage{
		ID:         uuid.New().String(),
		UserID:     userID,
		DocumentID: documentID,
		SessionID:  sessionID,
		Role:       "assistant",
		Message:    aiResponse,
	}

	if err := h.db.SaveChatMessage(assistantMessage); err != nil {
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error:   "server_error",
			Message: "Failed to save response",
		})
		return
	}

	c.JSON(http.StatusOK, models.ChatResponse{
		Response:  aiResponse,
		SessionID: sessionID,
		Timestamp: time.Now(),
	})
}

func (h *ChatHandler) GetHistory(c *gin.Context) {
	userID := c.GetString("user_id")
	documentID := c.Param("id")
	sessionID := c.Query("session_id")

	history, err := h.db.GetChatHistory(documentID, sessionID, userID, 50)
	if err != nil {
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error:   "server_error",
			Message: "Failed to fetch history",
		})
		return
	}

	if history == nil {
		history = []models.ChatMessage{}
	}

	c.JSON(http.StatusOK, models.ChatHistoryResponse{
		SessionID: sessionID,
		Messages:  history,
	})
}

func (h *ChatHandler) GetSessionHistory(c *gin.Context) {
	userID := c.GetString("user_id")
	sessionID := c.Param("sessionId")

	history, err := h.db.GetChatHistory("", sessionID, userID, 50)
	if err != nil {
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error:   "server_error",
			Message: "Failed to fetch history",
		})
		return
	}

	if history == nil {
		history = []models.ChatMessage{}
	}

	c.JSON(http.StatusOK, gin.H{
		"session_id": sessionID,
		"messages":   history,
	})
}

func (h *ChatHandler) callAIService(documentID, sessionID, message string) (string, error) {
	aiServiceURL := h.config.AIServiceURL
	if aiServiceURL == "" {
		aiServiceURL = "http://localhost:8000"
	}

	reqBody := map[string]string{
		"document_id": documentID,
		"session_id":  sessionID,
		"message":     message,
	}

	jsonBody, err := json.Marshal(reqBody)
	if err != nil {
		return "", err
	}

	resp, err := http.Post(
		aiServiceURL+"/api/v1/chat",
		"application/json",
		bytes.NewBuffer(jsonBody),
	)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return "", nil
	}

	var aiResp struct {
		Response string `json:"response"`
	}

	if err := json.NewDecoder(resp.Body).Decode(&aiResp); err != nil {
		return "", err
	}

	return aiResp.Response, nil
}

func sanitizeMessage(msg string) string {
	const maxLen = 10000
	if len(msg) > maxLen {
		msg = msg[:maxLen]
	}
	return msg
}
