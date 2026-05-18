package config

import (
	"fmt"
	"os"
	"path/filepath"
)

type Config struct {
	DatabaseURL        string
	RabbitMQURL        string
	AIServiceURL       string
	Port               string
	UploadsDir         string
	OutputsDir         string
	MaxFileSize        int64
	JWTSecret          string
	CORSAllowedOrigins string
	IsProduction       bool
}

func NewConfig() (*Config, error) {
	rootDir := getProjectRoot()

	cfg := &Config{
		DatabaseURL: getEnv(
			"DATABASE_URL",
			"postgresql://admin:admin123@localhost:5432/pdf_extractor",
		),

		RabbitMQURL: getEnv(
			"RABBITMQ_URL",
			"amqp://guest:guest@localhost:5672/",
		),

		AIServiceURL: getEnv(
			"AI_SERVICE_URL",
			"http://localhost:8000",
		),

		Port: getEnv("PORT", "8080"),

		UploadsDir: getEnv(
			"UPLOADS_DIR",
			filepath.Join(rootDir, "uploads"),
		),

		OutputsDir: getEnv(
			"OUTPUTS_DIR",
			filepath.Join(rootDir, "outputs"),
		),

		MaxFileSize: 100 * 1024 * 1024,

		JWTSecret: getEnv("JWT_SECRET", ""),

		CORSAllowedOrigins: getEnv(
			"CORS_ALLOWED_ORIGINS",
			"http://localhost:3000",
		),

		IsProduction: os.Getenv("GIN_MODE") == "release",
	}

	if cfg.JWTSecret == "" {
		return nil, fmt.Errorf("JWT_SECRET environment variable is required")
	}

	return cfg, nil
}

func getProjectRoot() string {
	dir, err := os.Getwd()
	if err != nil {
		return "."
	}

	if filepath.Base(dir) == "backend" {
		return filepath.Dir(dir)
	}

	return dir
}

func getEnv(key, fallback string) string {
	val := os.Getenv(key)
	if val == "" {
		return fallback
	}

	return val
}
