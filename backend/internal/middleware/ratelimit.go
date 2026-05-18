package middleware

import (
	"net/http"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/ahmadhasanm/ai-document-extractor/internal/models"
)

type visitor struct {
	count   int
	expires time.Time
}

type RateLimiter struct {
	visitors map[string]*visitor
	mu       sync.Mutex
	max      int
	window   time.Duration
}

func NewRateLimiter(max int, window time.Duration) *RateLimiter {
	rl := &RateLimiter{
		visitors: make(map[string]*visitor),
		max:      max,
		window:   window,
	}

	go rl.cleanup()
	return rl
}

func (rl *RateLimiter) cleanup() {
	ticker := time.NewTicker(time.Minute)
	defer ticker.Stop()

	for range ticker.C {
		rl.mu.Lock()
		now := time.Now()
		for ip, v := range rl.visitors {
			if now.After(v.expires) {
				delete(rl.visitors, ip)
			}
		}
		rl.mu.Unlock()
	}
}

func (rl *RateLimiter) Limit() gin.HandlerFunc {
	return func(c *gin.Context) {
		ip := c.ClientIP()

		rl.mu.Lock()
		defer rl.mu.Unlock()

		v, exists := rl.visitors[ip]
		now := time.Now()

		if !exists || now.After(v.expires) {
			rl.visitors[ip] = &visitor{
				count:   1,
				expires: now.Add(rl.window),
			}
			c.Next()
			return
		}

		v.count++
		if v.count > rl.max {
			c.Header("Retry-After", "60")
			c.AbortWithStatusJSON(http.StatusTooManyRequests, models.ErrorResponse{
				Error:   "rate_limited",
				Message: "Too many requests. Please try again later.",
			})
			return
		}

		c.Next()
	}
}
