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

// CreateChatSession creates a new chat session
func (h *ChatHandler) CreateChatSession(c *gin.Context) {
	var req models.CreateChatSessionRequest

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, models.ErrorResponse{
			Error:   "bad_request",
			Message: err.Error(),
		})
		return
	}

	// Generate title from first message if not provided
	if req.Title == "" {
		req.Title = "New Chat"
	}

	session := &models.ChatSession{
		ID:         uuid.New().String(),
		DocumentID: req.DocumentID,
		Title:      req.Title,
	}

	if err := h.db.CreateChatSession(session); err != nil {
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error:   "database_error",
			Message: err.Error(),
		})
		return
	}

	c.JSON(http.StatusCreated, models.CreateChatSessionResponse{
		SessionID: session.ID,
		Title:     session.Title,
		CreatedAt: session.CreatedAt,
	})
}

// ListChatSessions returns all chat sessions
func (h *ChatHandler) ListChatSessions(c *gin.Context) {
	sessions, err := h.db.ListChatSessions(50, 0)
	if err != nil {
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error:   "database_error",
			Message: err.Error(),
		})
		return
	}

	c.JSON(http.StatusOK, models.ListChatSessionsResponse{
		Sessions: sessions,
	})
}

// GetChatSession returns a specific chat session
func (h *ChatHandler) GetChatSession(c *gin.Context) {
	sessionID := c.Param("id")

	session, err := h.db.GetChatSession(sessionID)
	if err != nil {
		c.JSON(http.StatusNotFound, models.ErrorResponse{
			Error:   "not_found",
			Message: "Chat session not found",
		})
		return
	}

	c.JSON(http.StatusOK, session)
}

// DeleteChatSession deletes a chat session
func (h *ChatHandler) DeleteChatSession(c *gin.Context) {
	sessionID := c.Param("id")

	if err := h.db.DeleteChatSession(sessionID); err != nil {
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error:   "database_error",
			Message: err.Error(),
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Chat session deleted"})
}

// Chat sends a message and gets AI response
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

	// Save user message
	userMessage := &models.ChatMessage{
		ID:         uuid.New().String(),
		DocumentID: documentID,
		SessionID:  req.SessionID,
		Role:       "user",
		Message:    req.Message,
	}

	if err := h.db.SaveChatMessage(userMessage); err != nil {
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error:   "database_error",
			Message: "Failed to save user message: " + err.Error(),
		})
		return
	}

	// Call AI service for RAG response
	aiResponse, err := h.callAIService(documentID, req.SessionID, req.Message)
	if err != nil {
		// Fallback response if AI service fails
		aiResponse = "I apologize, but I'm having trouble processing your request right now. Please try again later."
	}

	// Save AI response
	assistantMessage := &models.ChatMessage{
		ID:         uuid.New().String(),
		DocumentID: documentID,
		SessionID:  req.SessionID,
		Role:       "assistant",
		Message:    aiResponse,
	}

	if err := h.db.SaveChatMessage(assistantMessage); err != nil {
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error:   "database_error",
			Message: "Failed to save assistant message: " + err.Error(),
		})
		return
	}

	c.JSON(http.StatusOK, models.ChatResponse{
		Response:  aiResponse,
		SessionID: req.SessionID,
		Timestamp: time.Now(),
	})
}

// ChatWithSession sends a message to a specific chat session (no document ID in path)
func (h *ChatHandler) ChatWithSession(c *gin.Context) {
	sessionID := c.Param("sessionId")

	var req models.ChatRequest

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, models.ErrorResponse{
			Error:   "bad_request",
			Message: err.Error(),
		})
		return
	}

	// Get session to find document ID
	session, err := h.db.GetChatSession(sessionID)
	if err != nil {
		c.JSON(http.StatusNotFound, models.ErrorResponse{
			Error:   "not_found",
			Message: "Chat session not found",
		})
		return
	}

	// Use document_id from request if provided, otherwise use session's document_id
	documentID := req.DocumentID
	if documentID == "" && session.DocumentID != nil {
		documentID = *session.DocumentID
	}

	// Save user message
	userMessage := &models.ChatMessage{
		ID:         uuid.New().String(),
		DocumentID: documentID,
		SessionID:  sessionID,
		Role:       "user",
		Message:    req.Message,
	}

	if err := h.db.SaveChatMessage(userMessage); err != nil {
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error:   "database_error",
			Message: "Failed to save user message: " + err.Error(),
		})
		return
	}

	// Call AI service for RAG response
	aiResponse, err := h.callAIService(documentID, sessionID, req.Message)
	if err != nil {
		aiResponse = "I apologize, but I'm having trouble processing your request right now. Please try again later."
	}

	// Save AI response
	assistantMessage := &models.ChatMessage{
		ID:         uuid.New().String(),
		DocumentID: documentID,
		SessionID:  sessionID,
		Role:       "assistant",
		Message:    aiResponse,
	}

	if err := h.db.SaveChatMessage(assistantMessage); err != nil {
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error:   "database_error",
			Message: "Failed to save assistant message: " + err.Error(),
		})
		return
	}

	c.JSON(http.StatusOK, models.ChatResponse{
		Response:  aiResponse,
		SessionID: sessionID,
		Timestamp: time.Now(),
	})
}

// GetHistory returns chat history for a document or session
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

	c.JSON(http.StatusOK, models.ChatHistoryResponse{
		SessionID: sessionID,
		Messages:  history,
	})
}

// GetSessionHistory returns chat history for a specific session
func (h *ChatHandler) GetSessionHistory(c *gin.Context) {
	sessionID := c.Param("sessionId")

	history, err := h.db.GetChatHistory("", sessionID, 50)
	if err != nil {
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error:   "database_error",
			Message: err.Error(),
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"session_id": sessionID,
		"messages":   history,
	})
}

// callAIService calls the AI service for RAG response
func (h *ChatHandler) callAIService(documentID, sessionID, message string) (string, error) {
	// AI service URL from config
	aiServiceURL := h.config.AIServiceURL
	if aiServiceURL == "" {
		aiServiceURL = "http://localhost:8000"
	}

	// Prepare request body
	reqBody := map[string]string{
		"document_id": documentID,
		"session_id":  sessionID,
		"message":     message,
	}

	jsonBody, err := json.Marshal(reqBody)
	if err != nil {
		return "", err
	}

	// Make request to AI service
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
		return "", nil // Return empty to trigger fallback
	}

	// Parse response
	var aiResp struct {
		Response string `json:"response"`
	}

	if err := json.NewDecoder(resp.Body).Decode(&aiResp); err != nil {
		return "", err
	}

	return aiResp.Response, nil
}