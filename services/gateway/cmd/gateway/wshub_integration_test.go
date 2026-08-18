//go:build integration

package main

import (
	"context"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
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

	rc, err := tcredis.Run(ctx, "redis:7.4.2-alpine@sha256:02419de7eddf55aa5bcf49efb74e88fa8d931b4d77c07eff8a6b2144472b6952",
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
		"sub":       userID,
		"aud":       "university-ecosystem-api",
		"role":      role,
		"jti":       jti,
		"is_active": true,
		"iat":       time.Now().Unix(),
		"exp":       time.Now().Add(1 * time.Hour).Unix(),
	})
	tokenStr, err := token.SignedString(secret)
	require.NoError(t, err)
	return tokenStr
}

// TestIntegration_GatewayWSTicketRoutingAndRevocation verifies token validation,
// exact-upstream routing, header enrichment, ticket persistence, and revocation:
//
//	Client → POST /ws/ticket (with JWT)
//	  → Gateway validates JWT, adds X-User-ID, and proxies to Python Backend
//	  → Python Backend validates headers, creates a 64-char ticket in Redis, and returns it
//	  → Client upgrades connection to ws-hub using the ticket
//	  → a simulated ws-hub consumer atomically consumes the Redis ticket
func TestIntegration_GatewayWSTicketRoutingAndRevocation(t *testing.T) {
	const testJWTSecret = "my-test-secret-key-at-least-32-bytes-long" // pragma: allowlist secret

	// 1. Spin up shared Redis container
	rdb, redisConnStr := startRedisContainer(t)

	// 2. Mock the Python backend that receives proxied HTTP requests
	// and creates WebSocket tickets in Redis.
	backendCapturedHeaders := make(map[string]string)
	backendHits := 0
	backendServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		backendHits++
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
		backendCapturedHeaders["authorization"] = r.Header.Get("Authorization")
		backendCapturedHeaders["cookie"] = r.Header.Get("Cookie")
		backendCapturedHeaders["x-csrf-token"] = r.Header.Get("X-CSRF-Token")
		backendCapturedHeaders["x-user-id"] = r.Header.Get("X-User-ID")
		backendCapturedHeaders["x-session-id"] = r.Header.Get("X-Session-ID")
		backendCapturedHeaders["x-internal-signature"] = r.Header.Get("X-Internal-Signature")

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
		w.WriteHeader(http.StatusCreated)
		_ = json.NewEncoder(w).Encode(map[string]any{"ticket": ticket, "expires_in": 15})
	}))
	t.Cleanup(backendServer.Close)

	wsHubHits := 0
	wsHubServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		wsHubHits++
		w.WriteHeader(http.StatusTeapot)
	}))
	t.Cleanup(wsHubServer.Close)

	// 3. Configure and start Gateway Gin engine
	cfg := &config.Config{
		Port:                "8080",
		BackendURL:          backendServer.URL,
		WsHubURL:            wsHubServer.URL,
		RedisURL:            redisConnStr,
		RevocationRedisURL:  redisConnStr,
		JWTSecret:           testJWTSecret,
		JWTAudience:         "university-ecosystem-api",
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
	req.Header.Set("Cookie", "csrf_token=csrf-cookie; preference=dark")
	req.Header.Set("X-CSRF-Token", "csrf-cookie")
	req.Header.Set("X-User-ID", "spoofed-user")
	req.Header.Set("X-Session-ID", "spoofed-session")
	req.Header.Set("X-Internal-Signature", "spoofed-signature")

	resp, err := http.DefaultClient.Do(req)
	require.NoError(t, err)
	defer func() { _ = resp.Body.Close() }()

	// Assert response from Gateway
	require.Equal(t, http.StatusCreated, resp.StatusCode)

	var result struct {
		Ticket    string `json:"ticket"`
		ExpiresIn int    `json:"expires_in"`
	}
	err = json.NewDecoder(resp.Body).Decode(&result)
	require.NoError(t, err)

	ticket := result.Ticket
	require.Len(t, ticket, 64, "Ticket must be 64 characters (hex)")
	require.Equal(t, 15, result.ExpiresIn)

	// 5. Verify the exact ticket route reached the backend, not ws-hub, and
	// client-spoofed identity headers were replaced by signed gateway identity.
	require.Equal(t, 1, backendHits)
	require.Zero(t, wsHubHits)
	require.Equal(t, "Bearer "+tokenStr, backendCapturedHeaders["authorization"])
	require.Equal(t, "csrf_token=csrf-cookie; preference=dark", backendCapturedHeaders["cookie"])
	require.Equal(t, "csrf-cookie", backendCapturedHeaders["x-csrf-token"])
	require.Equal(t, testUserID, backendCapturedHeaders["x-user-id"])
	require.Equal(t, "test-jti-123", backendCapturedHeaders["x-session-id"])
	mac := hmac.New(sha256.New, []byte("internal-secret"))
	_, err = mac.Write([]byte(testUserID + ":test-jti-123"))
	require.NoError(t, err)
	require.Equal(t, hex.EncodeToString(mac.Sum(nil)), backendCapturedHeaders["x-internal-signature"])

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

	// A revoked JTI must be denied at the gateway without reaching either
	// upstream, even though its signature and temporal claims are valid.
	require.NoError(t, rdb.Set(ctx, "revoked:jti:revoked-jti", "1", time.Minute).Err())
	revokedToken := generateTestJWT(t, []byte(testJWTSecret), testUserID, testRole, "revoked-jti")
	revokedReq, err := http.NewRequest(http.MethodPost, gatewayServer.URL+"/ws/ticket", nil)
	require.NoError(t, err)
	revokedReq.Header.Set("Authorization", "Bearer "+revokedToken)
	revokedResp, err := http.DefaultClient.Do(revokedReq)
	require.NoError(t, err)
	defer func() { _ = revokedResp.Body.Close() }()
	require.Equal(t, http.StatusUnauthorized, revokedResp.StatusCode)
	require.Equal(t, 1, backendHits)
	require.Zero(t, wsHubHits)
}
