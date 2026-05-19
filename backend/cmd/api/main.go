package main

import (
	"log"
	"os"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/joho/godotenv"
	"github.com/ahmadhasanm/ai-document-extractor/internal/config"
	"github.com/ahmadhasanm/ai-document-extractor/internal/database"
	"github.com/ahmadhasanm/ai-document-extractor/internal/handlers"
	"github.com/ahmadhasanm/ai-document-extractor/internal/middleware"
	"github.com/ahmadhasanm/ai-document-extractor/internal/queue"
)

func main() {
	// Load environment variables
	if err := godotenv.Load(); err != nil {
		log.Println("No .env file found, using environment variables")
	}

	// Initialize configuration (validates required env vars)
	cfg, err := config.NewConfig()
	if err != nil {
		log.Fatalf("Configuration error: %v", err)
	}

	// Set Gin mode
	if cfg.IsProduction {
		gin.SetMode(gin.ReleaseMode)
	}

	log.Println("UploadsDir:", cfg.UploadsDir)
	log.Println("OutputsDir:", cfg.OutputsDir)
	log.Println("Production mode:", cfg.IsProduction)

	// Initialize database
	db, err := database.NewDatabase(cfg.DatabaseURL)
	if err != nil {
		log.Fatalf("Failed to connect to database: %v", err)
	}
	defer db.Close()

	// Initialize RabbitMQ
	rabbitMQ, err := queue.NewRabbitMQ(cfg.RabbitMQURL)
	if err != nil {
		log.Fatalf("Failed to connect to RabbitMQ: %v", err)
	}
	defer rabbitMQ.Close()

	// Initialize Gin router
	router := gin.Default()

	// Apply middleware
	router.Use(middleware.CORSMiddleware(cfg.CORSAllowedOrigins))
	router.Use(middleware.LoggerMiddleware())
	router.Use(middleware.SecurityHeadersMiddleware(cfg.IsProduction))

	// Initialize handlers
	documentHandler := handlers.NewDocumentHandler(db, rabbitMQ, cfg)
	uploadHandler := handlers.NewUploadHandler(db, rabbitMQ, cfg)
	queueHandler := handlers.NewQueueHandler(db)
	chatHandler := handlers.NewChatHandler(db, cfg)
	authHandler := handlers.NewAuthHandler(db, cfg)

	// Rate limiters
	authRateLimiter := middleware.NewRateLimiter(10, time.Minute)
	chatRateLimiter := middleware.NewRateLimiter(30, time.Minute)
	uploadRateLimiter := middleware.NewRateLimiter(10, time.Minute)

	// Health check (public)
	router.GET("/health", func(c *gin.Context) {
		c.JSON(200, gin.H{
			"status":  "healthy",
			"service": "PDF Extractor Backend",
		})
	})

	// API routes
	api := router.Group("/api")
	{
		// Auth endpoints (public with rate limiting)
		api.POST("/auth/register", authRateLimiter.Limit(), authHandler.Register)
		api.POST("/auth/login", authRateLimiter.Limit(), authHandler.Login)
		api.GET("/auth/me", middleware.AuthMiddleware(cfg), authHandler.Me)

		// Public document image serving (accessed by <img> tags, no JWT possible)
		// Security: document IDs are UUIDs (unguessable), path traversal is blocked
		api.GET("/documents/:id/images/:filename", documentHandler.ServeImage)

		// Protected routes - require authentication
		protected := api.Group("")
		protected.Use(middleware.AuthMiddleware(cfg))
		{
			// Upload endpoints (rate limited)
			protected.POST("/upload", uploadRateLimiter.Limit(), uploadHandler.Upload)

			// Document endpoints
			protected.GET("/documents", documentHandler.List)
			protected.GET("/documents/:id", documentHandler.Get)
			protected.GET("/documents/:id/markdown", documentHandler.GetMarkdown)
			protected.GET("/documents/:id/json", documentHandler.GetJSON)
			protected.GET("/documents/:id/images", documentHandler.GetImages)
			protected.DELETE("/documents/:id", documentHandler.Delete)

			// Queue endpoints
			protected.GET("/queue/status", queueHandler.GetStatus)
			protected.GET("/queue/documents/:id", queueHandler.GetDocumentStatus)

			// Chat endpoints with rate limiting
			protected.POST("/chat/sessions", chatRateLimiter.Limit(), chatHandler.CreateChatSession)
			protected.GET("/chat/sessions", chatHandler.ListChatSessions)
			protected.GET("/chat/sessions/:sessionId", chatHandler.GetChatSession)
			protected.DELETE("/chat/sessions/:sessionId", chatHandler.DeleteChatSession)
			protected.GET("/chat/sessions/:sessionId/history", chatHandler.GetSessionHistory)
			protected.POST("/documents/:id/chat", chatRateLimiter.Limit(), chatHandler.Chat)
			protected.GET("/documents/:id/chat/history", chatHandler.GetHistory)
			protected.POST("/chat/sessions/:sessionId/messages", chatRateLimiter.Limit(), chatHandler.ChatWithSession)
		}
	}

	// Start server
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	log.Printf("Server starting on port %s", port)
	if err := router.Run(":" + port); err != nil {
		log.Fatalf("Failed to start server: %v", err)
	}
}
