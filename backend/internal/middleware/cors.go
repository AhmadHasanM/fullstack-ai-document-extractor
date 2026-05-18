package middleware

import (
	"strings"

	"github.com/gin-gonic/gin"
)

func CORSMiddleware(allowedOrigins string) gin.HandlerFunc {
	origins := strings.Split(allowedOrigins, ",")
	originMap := make(map[string]bool, len(origins))
	for _, o := range origins {
		originMap[strings.TrimSpace(o)] = true
	}

	return func(c *gin.Context) {
		origin := c.Request.Header.Get("Origin")

		if originMap[origin] {
			c.Writer.Header().Set("Access-Control-Allow-Origin", origin)
		} else if len(originMap) == 1 && originMap["*"] {
			c.Writer.Header().Set("Access-Control-Allow-Origin", "*")
		}

		c.Writer.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
		c.Writer.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")
		c.Writer.Header().Set("Access-Control-Allow-Credentials", "true")

		if c.Request.Method == "OPTIONS" {
			c.AbortWithStatus(204)
			return
		}

		c.Next()
	}
}
