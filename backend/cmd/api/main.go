package main

import (
	"log"
	"os"

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

	// Initialize configuration
	cfg := config.NewConfig()

	log.Println("UploadsDir:", cfg.UploadsDir)
	log.Println("OutputsDir:", cfg.OutputsDir)

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
	router.Use(middleware.CORSMiddleware())
	router.Use(middleware.LoggerMiddleware())

	// Initialize handlers
	documentHandler := handlers.NewDocumentHandler(db, rabbitMQ, cfg)
	uploadHandler := handlers.NewUploadHandler(db, rabbitMQ, cfg)
	queueHandler := handlers.NewQueueHandler(db)
	chatHandler := handlers.NewChatHandler(db, cfg)
	authHandler := handlers.NewAuthHandler(db, cfg)

	// Health check
	router.GET("/health", func(c *gin.Context) {
		c.JSON(200, gin.H{
			"status":  "healthy",
			"service": "PDF Extractor Backend",
		})
	})

	// API routes
	api := router.Group("/api")
	{
		// Auth endpoints (public)
		api.POST("/auth/register", authHandler.Register)
		api.POST("/auth/login", authHandler.Login)
		api.GET("/auth/me", middleware.AuthMiddleware(cfg), authHandler.Me)

		// Protected routes - require authentication
		protected := api.Group("")
		protected.Use(middleware.AuthMiddleware(cfg))
		{
			// Upload endpoints
			protected.POST("/upload", uploadHandler.Upload)

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

			// Chat endpoints
			// Sessions (no document required)
			protected.POST("/chat/sessions", chatHandler.CreateChatSession)
			protected.GET("/chat/sessions", chatHandler.ListChatSessions)
			protected.GET("/chat/sessions/:sessionId", chatHandler.GetChatSession)
			protected.DELETE("/chat/sessions/:sessionId", chatHandler.DeleteChatSession)
			protected.GET("/chat/sessions/:sessionId/history", chatHandler.GetSessionHistory)

			// Chat with document
			protected.POST("/documents/:id/chat", chatHandler.Chat)
			protected.GET("/documents/:id/chat/history", chatHandler.GetHistory)

			// Chat with session (no document in path)
			protected.POST("/chat/sessions/:sessionId/messages", chatHandler.ChatWithSession)
		}
	}

	// Serve static files (outputs)
	//router.Static("/outputs", "./outputs")
	//router.Static("/uploads", "./uploads")
	router.Static("/uploads", cfg.UploadsDir)
	router.Static("/outputs", cfg.OutputsDir)


	// Start server
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	log.Printf("🚀 Server starting on port %s", port)
	if err := router.Run(":" + port); err != nil {
		log.Fatalf("Failed to start server: %v", err)
	}
}