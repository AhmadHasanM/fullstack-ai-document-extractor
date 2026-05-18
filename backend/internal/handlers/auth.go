package handlers

import (
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
	"golang.org/x/crypto/bcrypt"

	"github.com/ahmadhasanm/ai-document-extractor/internal/config"
	"github.com/ahmadhasanm/ai-document-extractor/internal/database"
	"github.com/ahmadhasanm/ai-document-extractor/internal/models"
)

type AuthHandler struct {
	db     *database.Database
	config *config.Config
}

func NewAuthHandler(db *database.Database, cfg *config.Config) *AuthHandler {
	return &AuthHandler{
		db:     db,
		config: cfg,
	}
}

func (h *AuthHandler) Register(c *gin.Context) {
	var req models.RegisterRequest

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, models.ErrorResponse{
			Error:   "bad_request",
			Message: "Invalid request: " + err.Error(),
		})
		return
	}

	if len(req.Password) < 8 {
		c.JSON(http.StatusBadRequest, models.ErrorResponse{
			Error:   "bad_request",
			Message: "Password must be at least 8 characters",
		})
		return
	}

	existingUser, err := h.db.GetUserByEmail(req.Email)
	if err == nil && existingUser != nil {
		c.JSON(http.StatusConflict, models.ErrorResponse{
			Error:   "conflict",
			Message: "An account with this email already exists",
		})
		return
	}

	hashedPassword, err := bcrypt.GenerateFromPassword([]byte(req.Password), bcrypt.DefaultCost)
	if err != nil {
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error:   "server_error",
			Message: "Registration failed",
		})
		return
	}

	user := &models.User{
		ID:           uuid.New().String(),
		Email:        req.Email,
		PasswordHash: string(hashedPassword),
		Name:         &req.Name,
	}

	if err := h.db.CreateUser(user); err != nil {
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error:   "server_error",
			Message: "Registration failed",
		})
		return
	}

	token, err := h.generateToken(user)
	if err != nil {
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error:   "server_error",
			Message: "Registration failed",
		})
		return
	}

	c.JSON(http.StatusCreated, models.AuthResponse{
		Token: token,
		User: models.User{
			ID:        user.ID,
			Email:     user.Email,
			Name:      user.Name,
			CreatedAt: user.CreatedAt,
			UpdatedAt: user.UpdatedAt,
		},
	})
}

func (h *AuthHandler) Login(c *gin.Context) {
	var req models.LoginRequest

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, models.ErrorResponse{
			Error:   "bad_request",
			Message: "Invalid request",
		})
		return
	}

	user, err := h.db.GetUserByEmail(req.Email)
	if err != nil {
		c.JSON(http.StatusUnauthorized, models.ErrorResponse{
			Error:   "unauthorized",
			Message: "Invalid email or password",
		})
		return
	}

	if err := bcrypt.CompareHashAndPassword([]byte(user.PasswordHash), []byte(req.Password)); err != nil {
		c.JSON(http.StatusUnauthorized, models.ErrorResponse{
			Error:   "unauthorized",
			Message: "Invalid email or password",
		})
		return
	}

	token, err := h.generateToken(user)
	if err != nil {
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error:   "server_error",
			Message: "Login failed",
		})
		return
	}

	c.JSON(http.StatusOK, models.AuthResponse{
		Token: token,
		User: models.User{
			ID:        user.ID,
			Email:     user.Email,
			Name:      user.Name,
			CreatedAt: user.CreatedAt,
			UpdatedAt: user.UpdatedAt,
		},
	})
}

func (h *AuthHandler) Me(c *gin.Context) {
	userID, exists := c.Get("user_id")
	if !exists {
		c.JSON(http.StatusUnauthorized, models.ErrorResponse{
			Error:   "unauthorized",
			Message: "Not authenticated",
		})
		return
	}

	user, err := h.db.GetUserByID(userID.(string))
	if err != nil {
		c.JSON(http.StatusNotFound, models.ErrorResponse{
			Error:   "not_found",
			Message: "User not found",
		})
		return
	}

	c.JSON(http.StatusOK, user)
}

func (h *AuthHandler) generateToken(user *models.User) (string, error) {
	expirationTime := time.Now().Add(24 * time.Hour)

	claims := jwt.MapClaims{
		"user_id": user.ID,
		"email":   user.Email,
		"exp":     expirationTime.Unix(),
		"iat":     time.Now().Unix(),
	}

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	return token.SignedString([]byte(h.config.JWTSecret))
}
