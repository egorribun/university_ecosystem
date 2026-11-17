package middleware

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestRateLimiterRetryAfterRoundsUpRedisDelay(t *testing.T) {
	gin.SetMode(gin.TestMode)
	for _, tc := range []struct {
		name string
		rps  int
	}{
		{name: "whole second", rps: 1},
		{name: "half second", rps: 2},
		{name: "ten milliseconds", rps: 100},
	} {
		t.Run(tc.name, func(t *testing.T) {
			mr := miniredis.RunT(t)
			now := time.Unix(1_700_000_000, 0)
			mr.SetTime(now)
			rl, err := NewRateLimiter(t.Context(), "redis://"+mr.Addr(), tc.rps, 1)
			require.NoError(t, err)
			t.Cleanup(func() { assert.NoError(t, rl.Close()) })

			router := gin.New()
			router.Use(rl.Middleware(t.Context()))
			router.GET("/api/thing", func(c *gin.Context) { c.Status(http.StatusOK) })
			request := func() *httptest.ResponseRecorder {
				response := httptest.NewRecorder()
				req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/api/thing", nil)
				req.RemoteAddr = "203.0.113.7:1234"
				router.ServeHTTP(response, req)
				return response
			}

			require.Equal(t, http.StatusOK, request().Code)
			rejected := request()
			require.Equal(t, http.StatusTooManyRequests, rejected.Code)
			require.Equal(t, "1", rejected.Header().Get("Retry-After"))
			var body struct {
				RetryAfter int `json:"retry_after"`
			}
			require.NoError(t, json.Unmarshal(rejected.Body.Bytes(), &body))
			require.Equal(t, 1, body.RetryAfter)
			require.Empty(t, rl.fallbackCounters, "the real Redis result, not fallback, must be exercised")

			mr.SetTime(now.Add(time.Second))
			require.Equal(t, http.StatusOK, request().Code, "the advertised delay must allow replenishment")
		})
	}
}
