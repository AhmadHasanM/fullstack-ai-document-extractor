package middleware

import "github.com/gin-gonic/gin"

func SecurityHeadersMiddleware(isProduction bool) gin.HandlerFunc {
	return func(c *gin.Context) {
		c.Writer.Header().Set("X-Content-Type-Options", "nosniff")
		c.Writer.Header().Set("X-Frame-Options", "DENY")
		c.Writer.Header().Set("Referrer-Policy", "strict-origin-when-cross-origin")
		c.Writer.Header().Set(
			"Content-Security-Policy",
			"default-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob:; script-src 'self' 'unsafe-eval' 'unsafe-inline'; connect-src 'self' *;",
		)

		if isProduction {
			c.Writer.Header().Set("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
		}

		c.Next()
	}
}
