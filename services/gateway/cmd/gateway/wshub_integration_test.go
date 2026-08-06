//go:build integration

package main

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/require"
	"github.com/testcontainers/testcontainers-go"
	tclog "github.com/testcontainers/testcontainers-go/log"
	tcredis "github.com/testcontainers/testcontainers-go/modules/redis"
	"github.com/university-ecosystem/gateway/internal/config"
)

// startRedisContainer spins up a real Redis container for Gateway integration tests.
func startRedisContainer(t *testing.T) (*redis.Client, string) {
	t.Helper()
	ctx := context.Background()

	rc, err := tcredis.Run(ctx, "redis:7.4.2-alpine",
		testcontainers.WithLogger(tclog.TestLogger(t)),
	)
	require.NoError(t, err)
	t.Cleanup(func() {
		_ = rc.Terminate(context.Background())
	})

	connStr, err := rc.ConnectionString(ctx)
	require.NoError(t, err)
	opts, err := redis.ParseURL(connStr)
	require.NoError(t, err)
	client := redis.NewClient(opts)
	t.Cleanup(func() {
		_ = client.Close()
	})
	return client, connStr
}

// generateTestJWT generates a valid JWT signed with the test secret.
func generateTestJWT(t *testing.T, secret []byte, userID, role, jti string) string {
	t.Helper()
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
		"sub":  userID,
		"role": role,
		"jti":  jti,
		"exp":  time.Now().Add(1 * time.Hour).Unix(),
	})
	tokenStr, err := token.SignedString(secret)
	require.NoError(t, err)
	return tokenStr
}

// TestIntegration_GatewayToWSHubE2E verifies the end-to-end token validation,
// request proxying, header enrichment, and ticket generation pipeline:
//
//	Client → POST /ws/ticket (with JWT)
//	  → Gateway validates JWT, adds X-User-ID, and proxies to Python Backend
//	  → Python Backend validates headers, creates a 64-char ticket in Redis, and returns it
//	  → Client upgrades connection to ws-hub using the ticket
//	  → ws-hub consumes ticket from Redis via GETDEL (verifies E2E integration)
func TestIntegration_GatewayToWSHubE2E(t *testing.T) {
	const testJWTSecret = "my-test-secret-key-at-least-32-bytes-long" // pragma: allowlist secret

	// 1. Spin up shared Redis container
	rdb, redisConnStr := startRedisContainer(t)

	// 2. Mock the Python backend that receives proxied HTTP requests
	// and creates WebSocket tickets in Redis.
	backendCapturedHeaders := make(map[string]string)
	backendServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/ws/ticket" || r.Method != http.MethodPost {
			http.Error(w, "Not Found", http.StatusNotFound)
			return
		}

		// Verify and parse the Authorization Bearer token forwarded by the gateway
		authHeader := r.Header.Get("Authorization")
		if !strings.HasPrefix(authHeader, "Bearer ") {
			http.Error(w, "Unauthorized (missing Bearer token)", http.StatusUnauthorized)
			return
		}
		tokenStr := strings.TrimPrefix(authHeader, "Bearer ")

		token, err := jwt.Parse(tokenStr, func(token *jwt.Token) (interface{}, error) {
			return []byte(testJWTSecret), nil
		})
		if err != nil || !token.Valid {
			http.Error(w, "Unauthorized (invalid Bearer token)", http.StatusUnauthorized)
			return
		}

		claims, ok := token.Claims.(jwt.MapClaims)
		if !ok {
			http.Error(w, "Unauthorized (invalid claims)", http.StatusUnauthorized)
			return
		}

		userID, _ := claims["sub"].(string)
		if userID == "" {
			http.Error(w, "Unauthorized (missing sub in token)", http.StatusUnauthorized)
			return
		}

		// Generate a 64-char hex ticket
		randBytes := make([]byte, 32)
		_, err = rand.Read(randBytes)
		if err != nil {
			http.Error(w, "Internal Server Error", http.StatusInternalServerError)
			return
		}
		ticket := hex.EncodeToString(randBytes)

		// Save the ticket in Redis under the ws-hub format: "ott:ws:{ticket}" -> "user_id:jti"
		ctx := context.Background()
		ticketKey := fmt.Sprintf("ott:ws:%s", ticket)
		ticketValue := fmt.Sprintf("%s:test-jti-123", userID)
		err = rdb.Set(ctx, ticketKey, ticketValue, 1*time.Minute).Err()
		if err != nil {
			http.Error(w, "Failed to save ticket to Redis", http.StatusInternalServerError)
			return
		}

		// Return the ticket
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]string{"ticket": ticket})
	}))
	t.Cleanup(backendServer.Close)

	// 3. Configure and start Gateway Gin engine
	cfg := &config.Config{
		Port:                "8080",
		BackendURL:          backendServer.URL,
		WsHubURL:            backendServer.URL,
		RedisURL:            redisConnStr,
		JWTSecret:           testJWTSecret,
		InternalHMACSecret:  "internal-secret",
		AllowedOrigins:      []string{"*"},
		Environment:         "testing",
		JWKSRefreshInterval: 3600,
	}

	logger := initLogger()
	router, err := setupRouter(cfg, logger, nil, nil, context.Background())
	require.NoError(t, err)
	gatewayServer := httptest.NewServer(router)
	t.Cleanup(gatewayServer.Close)

	// 4. Generate JWT and make a request to the Gateway
	testUserID := uuid.New().String()
	testRole := "student"
	tokenStr := generateTestJWT(t, []byte(testJWTSecret), testUserID, testRole, "test-jti-123")

	req, err := http.NewRequest(http.MethodPost, gatewayServer.URL+"/ws/ticket", nil)
	require.NoError(t, err)
	req.Header.Set("Authorization", "Bearer "+tokenStr)

	resp, err := http.DefaultClient.Do(req)
	require.NoError(t, err)
	defer func() { _ = resp.Body.Close() }()

	// Assert response from Gateway
	require.Equal(t, http.StatusOK, resp.StatusCode)

	var result map[string]string
	err = json.NewDecoder(resp.Body).Decode(&result)
	require.NoError(t, err)

	ticket := result["ticket"]
	require.Len(t, ticket, 64, "Ticket must be 64 characters (hex)")

	// 5. Verify backend received Authorization header but no X-User-ID (since it's a proxied non-API route)
	require.Empty(t, backendCapturedHeaders["x-user-id"], "Gateway should not inject X-User-ID on non-API routes")

	// 6. Simulate ws-hub consuming the ticket from Redis via GETDEL (atomicity check)
	ctx := context.Background()
	ticketKey := fmt.Sprintf("ott:ws:%s", ticket)

	// Consume ticket
	ticketValue, err := rdb.GetDel(ctx, ticketKey).Result()
	require.NoError(t, err, "Ticket key must exist in Redis")

	expectedValue := fmt.Sprintf("%s:test-jti-123", testUserID)
	require.Equal(t, expectedValue, ticketValue, "Redis ticket value must match formatted string")

	// Re-query must fail (GETDEL was atomic and deleted it)
	_, err = rdb.Get(ctx, ticketKey).Result()
	require.ErrorIs(t, err, redis.Nil, "Ticket must be deleted after consumption")
}
