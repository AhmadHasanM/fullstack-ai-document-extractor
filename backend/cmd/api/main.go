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
		// Upload endpoints
		api.POST("/upload", uploadHandler.Upload)

		// Document endpoints
		api.GET("/documents", documentHandler.List)
		api.GET("/documents/:id", documentHandler.Get)
		api.GET("/documents/:id/markdown", documentHandler.GetMarkdown)
		api.GET("/documents/:id/json", documentHandler.GetJSON)
		api.GET("/documents/:id/images", documentHandler.GetImages)
		api.DELETE("/documents/:id", documentHandler.Delete)

		// Queue endpoints
		api.GET("/queue/status", queueHandler.GetStatus)
		api.GET("/queue/documents/:id", queueHandler.GetDocumentStatus)

		// Chat endpoints
		api.POST("/documents/:id/chat", chatHandler.Chat)
		api.GET("/documents/:id/chat/history", chatHandler.GetHistory)
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