package hub

// Coverage tests (testing session 9) for the WebSocket upgrade path:
// validateUpgradeTicket (mock RESP server — idiom ported from
// services/cmd/uni-cli/main_test.go), RS256 + JWKS validation via an
// httptest JWKS server, and the full HandleWebSocket upgrade → join →
// broadcast → deliver E2E flow with a real gorilla/websocket dial.
//
// CAUTION (documented in the session-9 plan): never send {"type":"message"}
// frames through ReadPump in these tests — handleMessage publishes to a nil
// *nats.Conn and the panic inside the ReadPump goroutine would kill the test
// binary. The join/leave message types are NATS-free and safe.

import (
	"context"
	"crypto/rand"
	"crypto/rsa"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/gorilla/websocket"
	"github.com/lestrrat-go/jwx/v2/jwk"
	goredis "github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/ws-hub/pkg/config"
)

// ---------------------------------------------------------------------------
// Mock RESP server (GETDEL-aware) — ported from uni-cli's setupMockRedisServer
// ---------------------------------------------------------------------------

// startTicketRESPServer serves the minimal RESP dialect go-redis needs for
// ticket validation. getdelReply == "" replies nil ($-1) — ticket not found.
// respondTicketRESP writes a canned RESP reply for the uppercased request
// fragment. Extracted from the accept loop to keep startTicketRESPServer under
// the gocognit gate (mirrors the respondRESP idiom in cmd/uni-cli/main_test.go).
func respondTicketRESP(write func(string), upper, getdelReply string) {
	switch {
	case strings.Contains(upper, "HELLO"):
		write("-ERR unknown command 'HELLO'\r\n")
	case strings.Contains(upper, "CLIENT"):
		write("-ERR unknown command 'CLIENT'\r\n")
	case strings.Contains(upper, "PING"):
		write("+PONG\r\n")
	case strings.Contains(upper, "GETDEL"):
		if getdelReply == "" {
			write("$-1\r\n") // RESP nil bulk string → ticket not found
		} else {
			write(fmt.Sprintf("$%d\r\n%s\r\n", len(getdelReply), getdelReply))
		}
	default:
		write("+OK\r\n")
	}
}

// handleTicketConn serves one mock-Redis connection until it closes.
func handleTicketConn(c net.Conn, getdelReply string) {
	defer func() { _ = c.Close() }()                      //nolint:errcheck // mock cleanup
	write := func(s string) { _, _ = c.Write([]byte(s)) } //nolint:errcheck // best-effort
	buf := make([]byte, 2048)
	for {
		n, err := c.Read(buf)
		if err != nil {
			return
		}
		for _, part := range strings.Split(string(buf[:n]), "*") {
			if part == "" {
				continue
			}
			respondTicketRESP(write, strings.ToUpper(part), getdelReply)
		}
	}
}

func startTicketRESPServer(t *testing.T, getdelReply string) string {
	t.Helper()
	var lc net.ListenConfig
	ln, err := lc.Listen(context.Background(), "tcp", "127.0.0.1:0")
	require.NoError(t, err)
	t.Cleanup(func() { _ = ln.Close() }) //nolint:errcheck // mock server cleanup

	go func() {
		for {
			conn, err := ln.Accept()
			if err != nil {
				return
			}
			go handleTicketConn(conn, getdelReply)
		}
	}()
	return ln.Addr().String()
}

func hubWithTicketRedis(t *testing.T, getdelReply string) *Hub {
	t.Helper()
	addr := startTicketRESPServer(t, getdelReply)
	h := setupTestHub()
	h.redisClient = goredis.NewClient(&goredis.Options{Addr: addr})
	t.Cleanup(func() { _ = h.redisClient.Close() }) //nolint:errcheck // test cleanup
	return h
}

const validTicket = "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff" // pragma: allowlist secret

// ---------------------------------------------------------------------------
// validateUpgradeTicket
// ---------------------------------------------------------------------------

func TestValidateUpgradeTicket_NoRedisConfigured(t *testing.T) {
	h := setupTestHub() // redisClient nil
	_, err := h.validateUpgradeTicket(context.Background(), validTicket)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "redis not available")
}

func TestValidateUpgradeTicket_RejectsBadFormat(t *testing.T) {
	// Format checks run after the nil-redis guard, so a (never-reached)
	// RESP server is required for these cases to hit the format branches.
	h := hubWithTicketRedis(t, "unused:unused")
	cases := []struct {
		name   string
		ticket string
		errSub string
	}{
		{"too short", "abc123", "invalid ticket length"},
		{"too long", strings.Repeat("a", 65), "invalid ticket length"},
		{"bad charset uppercase", strings.Repeat("A", 64), "invalid ticket charset"},
		{"bad charset symbol", strings.Repeat("a", 63) + "!", "invalid ticket charset"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			_, err := h.validateUpgradeTicket(context.Background(), tc.ticket)
			require.Error(t, err)
			assert.Contains(t, err.Error(), tc.errSub)
		})
	}
}

func TestValidateUpgradeTicket_NotFound(t *testing.T) {
	h := hubWithTicketRedis(t, "") // GETDEL → nil
	_, err := h.validateUpgradeTicket(context.Background(), validTicket)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "not found or already used")
}

func TestValidateUpgradeTicket_MalformedPayloads(t *testing.T) {
	cases := []struct {
		name  string
		reply string
	}{
		{"no colon", "user-without-jti"},
		{"empty user", ":jti-only"},
		{"trailing colon", "user-1:"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			h := hubWithTicketRedis(t, tc.reply)
			_, err := h.validateUpgradeTicket(context.Background(), validTicket)
			require.Error(t, err)
			assert.Contains(t, err.Error(), "malformed ticket payload")
		})
	}
}

func TestValidateUpgradeTicket_HappyPath(t *testing.T) {
	h := hubWithTicketRedis(t, "user-77:jti-42")
	userID, err := h.validateUpgradeTicket(context.Background(), validTicket)
	require.NoError(t, err)
	assert.Equal(t, "user-77", userID)
}

// ---------------------------------------------------------------------------
// RS256 / JWKS validation
// ---------------------------------------------------------------------------

func startJWKSServer(t *testing.T, pub *rsa.PublicKey, kid string) *httptest.Server {
	t.Helper()
	key, err := jwk.FromRaw(pub)
	require.NoError(t, err)
	require.NoError(t, key.Set(jwk.KeyIDKey, kid))
	require.NoError(t, key.Set(jwk.AlgorithmKey, "RS256"))
	set := jwk.NewSet()
	require.NoError(t, set.AddKey(key))
	body, err := json.Marshal(set)
	require.NoError(t, err)

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write(body) //nolint:errcheck // test server best-effort
	}))
	t.Cleanup(srv.Close)
	return srv
}

func signRS256(t *testing.T, priv *rsa.PrivateKey, kid string, claims jwt.MapClaims) string {
	t.Helper()
	token := jwt.NewWithClaims(jwt.SigningMethodRS256, claims)
	token.Header["kid"] = kid
	signed, err := token.SignedString(priv)
	require.NoError(t, err)
	return signed
}

func TestSetupJWKS_EmptyURLIsNoop(t *testing.T) {
	h := setupTestHub()
	require.NoError(t, h.SetupJWKS(context.Background(), ""))
	assert.False(t, h.HasJWKSCache())
}

func TestValidateToken_RS256Paths(t *testing.T) {
	priv, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)
	srv := startJWKSServer(t, &priv.PublicKey, "kid-1")

	h := setupTestHub()
	ctx := context.Background()
	require.NoError(t, h.SetupJWKS(ctx, srv.URL))
	assert.True(t, h.HasJWKSCache())

	t.Run("valid token returns sub", func(t *testing.T) {
		token := signRS256(t, priv, "kid-1", jwt.MapClaims{
			"sub": "user-rs",
			"exp": time.Now().Add(time.Hour).Unix(),
		})
		sub, err := h.ValidateToken(ctx, token, nil)
		require.NoError(t, err)
		assert.Equal(t, "user-rs", sub)
	})

	t.Run("expired token rejected", func(t *testing.T) {
		token := signRS256(t, priv, "kid-1", jwt.MapClaims{
			"sub": "user-rs",
			"exp": time.Now().Add(-time.Hour).Unix(),
		})
		_, err := h.ValidateToken(ctx, token, nil)
		require.Error(t, err)
	})

	t.Run("missing sub rejected", func(t *testing.T) {
		token := signRS256(t, priv, "kid-1", jwt.MapClaims{
			"exp": time.Now().Add(time.Hour).Unix(),
		})
		_, err := h.ValidateToken(ctx, token, nil)
		require.Error(t, err)
	})

	t.Run("unknown kid triggers force-refresh retry then rejects", func(t *testing.T) {
		// Reset the package-level cooldown so tryForceRefreshJWKS actually fires.
		_lastJWKSForceRefreshUnix.Store(0)
		token := signRS256(t, priv, "kid-unknown", jwt.MapClaims{
			"sub": "user-rs",
			"exp": time.Now().Add(time.Hour).Unix(),
		})
		_, err := h.ValidateToken(ctx, token, nil)
		require.Error(t, err)
		assert.Contains(t, err.Error(), "invalid RS256 token")
	})

	t.Run("unsupported algorithm rejected", func(t *testing.T) {
		// HS384-signed token → neither RS256 nor HS256 path accepts it.
		hsToken := jwt.NewWithClaims(jwt.SigningMethodHS384, jwt.MapClaims{"sub": "x"})
		signed, err := hsToken.SignedString([]byte("secret")) // pragma: allowlist secret
		require.NoError(t, err)
		_, err = h.ValidateToken(ctx, signed, nil)
		require.Error(t, err)
		assert.Contains(t, err.Error(), "unsupported JWT algorithm")
	})
}

func TestValidateRS256_WithoutJWKSConfigured(t *testing.T) {
	h := setupTestHub()
	priv, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)
	token := signRS256(t, priv, "kid-x", jwt.MapClaims{
		"sub": "u",
		"exp": time.Now().Add(time.Hour).Unix(),
	})
	_, err = h.ValidateToken(context.Background(), token, nil)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "JWKS not configured")
}

// ---------------------------------------------------------------------------
// HandleWebSocket — full upgrade → join → broadcast → deliver E2E
// ---------------------------------------------------------------------------

func TestHandleWebSocket_E2EUpgradeJoinAndDeliver(t *testing.T) {
	h := hubWithTicketRedis(t, "user-e2e:jti-1")
	cfg := &config.Config{SendBufferSize: 8}

	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{})
	go func() {
		defer close(done)
		h.Run(ctx)
	}()
	defer func() { cancel(); <-done }()

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		h.HandleWebSocket(w, r, cfg)
	}))
	defer srv.Close()

	wsURL := "ws" + strings.TrimPrefix(srv.URL, "http") + "?ticket=" + validTicket
	conn, resp, err := websocket.DefaultDialer.Dial(wsURL, nil)
	require.NoError(t, err)
	if resp != nil && resp.Body != nil {
		_ = resp.Body.Close() //nolint:errcheck // handshake response cleanup
	}
	defer func() { _ = conn.Close() }() //nolint:errcheck // test cleanup

	// Registered under the ticket's user id.
	require.Eventually(t, func() bool {
		h.mu.RLock()
		defer h.mu.RUnlock()
		_, ok := h.Clients["user-e2e"]
		return ok
	}, 2*time.Second, 10*time.Millisecond)

	// Join a room through ReadPump (NATS-free message type).
	require.NoError(t, conn.WriteJSON(map[string]string{"type": "join", "room": "room-e2e"}))
	require.Eventually(t, func() bool {
		h.mu.RLock()
		defer h.mu.RUnlock()
		return len(h.Rooms["room-e2e"]) == 1
	}, 2*time.Second, 10*time.Millisecond)

	// Room broadcast must reach the dialed connection through WritePump.
	h.Broadcast <- &Message{Type: "room-news", Room: "room-e2e", Payload: []byte(`{"k":"v"}`)}
	require.NoError(t, conn.SetReadDeadline(time.Now().Add(2*time.Second)))
	var got Message
	require.NoError(t, conn.ReadJSON(&got))
	assert.Equal(t, "room-news", got.Type)
	assert.Equal(t, "room-e2e", got.Room)

	// Closing the socket unregisters the client via ReadPump teardown.
	require.NoError(t, conn.Close())
	require.Eventually(t, func() bool {
		h.mu.RLock()
		defer h.mu.RUnlock()
		_, ok := h.Clients["user-e2e"]
		return !ok
	}, 2*time.Second, 10*time.Millisecond)
}

func TestHandleWebSocket_RejectsDisallowedOrigin(t *testing.T) {
	origEnv := os.Getenv("ENVIRONMENT")
	os.Setenv("ENVIRONMENT", "production")
	defer os.Setenv("ENVIRONMENT", origEnv)

	SetAllowedOrigins([]string{"http://allowed.example"})
	defer SetAllowedOrigins(nil)

	h := hubWithTicketRedis(t, "user-origin:jti-1")
	cfg := &config.Config{SendBufferSize: 8}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		h.HandleWebSocket(w, r, cfg)
	}))
	defer srv.Close()

	wsURL := "ws" + strings.TrimPrefix(srv.URL, "http") + "?ticket=" + validTicket
	header := http.Header{"Origin": []string{"http://evil.example"}}
	conn, resp, err := websocket.DefaultDialer.Dial(wsURL, header) //nolint:bodyclose // closed below when non-nil
	require.Error(t, err)
	if resp != nil && resp.Body != nil {
		_ = resp.Body.Close() //nolint:errcheck // handshake response cleanup
	}
	if conn != nil {
		_ = conn.Close() //nolint:errcheck // defensive
	}
}

func TestHandleWebSocket_InvalidTicketRejected(t *testing.T) {
	h := hubWithTicketRedis(t, "") // GETDEL nil → ticket not found
	cfg := &config.Config{SendBufferSize: 8}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		h.HandleWebSocket(w, r, cfg)
	}))
	defer srv.Close()

	resp, err := http.Get(srv.URL + "?ticket=" + validTicket) //nolint:noctx // plain GET against local test server
	require.NoError(t, err)
	defer func() { _ = resp.Body.Close() }() //nolint:errcheck // test cleanup
	assert.Equal(t, http.StatusUnauthorized, resp.StatusCode)
}

// ---------------------------------------------------------------------------
// validateHMAC — direct branch coverage (testing session 11)
//
// ValidateToken routes by the token's alg header BEFORE calling validateHMAC,
// so the wrong-alg branch inside validateHMAC's keyFunc is unreachable through
// ValidateToken. These tests call (*Hub).validateHMAC directly (white-box, same
// package) to cover every branch of handlers.go:352-380.
// ---------------------------------------------------------------------------

// signHS256 forges an HS256 token signed with secret (mirrors the inline forge
// pattern already used in hub_test.go).
func signHS256(t *testing.T, secret string, claims jwt.MapClaims) string {
	t.Helper()
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	signed, err := token.SignedString([]byte(secret))
	require.NoError(t, err)
	return signed
}

func TestValidateHMAC_EmptySecrets(t *testing.T) {
	h := setupTestHub()
	// len(secrets) == 0 → handlers.go:354 returns jwt.ErrTokenSignatureInvalid directly.
	sub, err := h.validateHMAC("any.token.value", nil)
	assert.Empty(t, sub)
	assert.ErrorIs(t, err, jwt.ErrTokenSignatureInvalid)

	// Also exercise the explicit empty-slice form.
	_, err = h.validateHMAC("any.token.value", []string{})
	assert.ErrorIs(t, err, jwt.ErrTokenSignatureInvalid)
}

func TestValidateHMAC_WrongAlg(t *testing.T) {
	h := setupTestHub()
	secret := "hmac-secret" // pragma: allowlist secret

	t.Run("RS256-signed token hits unexpected-signing-method", func(t *testing.T) {
		priv, err := rsa.GenerateKey(rand.Reader, 2048)
		require.NoError(t, err)
		rsToken := signRS256(t, priv, "kid-x", jwt.MapClaims{
			"sub": "user-rs",
			"exp": time.Now().Add(time.Hour).Unix(),
		})
		// Direct call — keyFunc rejects t.Method != HS256 → lastErr → returned at :377.
		sub, err := h.validateHMAC(rsToken, []string{secret})
		assert.Empty(t, sub)
		require.Error(t, err)
		assert.Contains(t, err.Error(), "unexpected signing method")
	})

	t.Run("none-alg token hits unexpected-signing-method", func(t *testing.T) {
		noneTok := jwt.New(jwt.SigningMethodNone)
		noneTok.Claims = jwt.MapClaims{"sub": "user-none"}
		signed, err := noneTok.SignedString(jwt.UnsafeAllowNoneSignatureType)
		require.NoError(t, err)
		sub, err := h.validateHMAC(signed, []string{secret})
		assert.Empty(t, sub)
		require.Error(t, err)
	})
}

func TestValidateHMAC_MissingSubClaim(t *testing.T) {
	h := setupTestHub()
	secret := "hmac-secret" // pragma: allowlist secret
	// Valid signature + valid claims, but no "sub" → handlers.go:373 returns
	// jwt.ErrTokenInvalidClaims directly.
	token := signHS256(t, secret, jwt.MapClaims{
		"exp": time.Now().Add(time.Hour).Unix(),
		// deliberately no "sub"
	})
	sub, err := h.validateHMAC(token, []string{secret})
	assert.Empty(t, sub)
	assert.ErrorIs(t, err, jwt.ErrTokenInvalidClaims)
}

func TestValidateHMAC_MultiSecretRotation(t *testing.T) {
	h := setupTestHub()
	oldSecret := "old-rotated-out-secret" // pragma: allowlist secret
	newSecret := "new-rotated-out-secret" // pragma: allowlist secret
	// Signed with the SECOND secret → first secret's Parse fails (lastErr set,
	// continue), second secret succeeds → loop returns sub at :371.
	token := signHS256(t, newSecret, jwt.MapClaims{
		"sub": "user-rotated",
		"exp": time.Now().Add(time.Hour).Unix(),
	})
	sub, err := h.validateHMAC(token, []string{oldSecret, newSecret})
	require.NoError(t, err)
	assert.Equal(t, "user-rotated", sub)
}

func TestValidateHMAC_AllSecretsFail(t *testing.T) {
	h := setupTestHub()
	token := signHS256(t, "the-real-secret", jwt.MapClaims{ // pragma: allowlist secret
		"sub": "user-x",
		"exp": time.Now().Add(time.Hour).Unix(),
	})
	// Neither candidate secret matches → both Parse calls fail, lastErr returned
	// at handlers.go:377. jwt/v5 joins ErrTokenSignatureInvalid into the parse
	// error, so errors.Is unwraps it (assert.Equal would FAIL — it's wrapped).
	sub, err := h.validateHMAC(token, []string{"wrong-1", "wrong-2"}) // pragma: allowlist secret
	assert.Empty(t, sub)
	require.Error(t, err)
	assert.ErrorIs(t, err, jwt.ErrTokenSignatureInvalid)
}

func TestValidateHMAC_ValidHS256(t *testing.T) {
	h := setupTestHub()
	secret := "hmac-secret" // pragma: allowlist secret
	token := signHS256(t, secret, jwt.MapClaims{
		"sub": "user-ok",
		"exp": time.Now().Add(time.Hour).Unix(),
	})
	sub, err := h.validateHMAC(token, []string{secret})
	require.NoError(t, err)
	assert.Equal(t, "user-ok", sub)
}

func signRS512(t *testing.T, key *rsa.PrivateKey, kid string, claims jwt.Claims) string {
	t.Helper()
	token := jwt.NewWithClaims(jwt.SigningMethodRS512, claims)
	token.Header["kid"] = kid
	str, err := token.SignedString(key)
	require.NoError(t, err)
	return str
}

func TestValidateRS256_EdgeCases(t *testing.T) {
	ctx := context.Background()
	priv, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)
	pub := &priv.PublicKey

	// Setup JWKS server
	jwksMap := map[string]interface{}{
		"keys": []map[string]interface{}{
			{
				"kty": "RSA",
				"kid": "kid-1",
				"n":   jwt.NewNumericDate(time.Now()).String(), // mock placeholder n/e
				"e":   "AQAB",
			},
		},
	}
	// Better yet, use real JWK format
	key, err := jwk.FromRaw(pub)
	require.NoError(t, err)
	_ = key.Set(jwk.KeyIDKey, "kid-1")
	buf, err := json.Marshal(key)
	require.NoError(t, err)
	var jwkKey map[string]interface{}
	require.NoError(t, json.Unmarshal(buf, &jwkKey))
	jwksMap = map[string]interface{}{
		"keys": []map[string]interface{}{jwkKey},
	}

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(jwksMap)
	}))
	defer server.Close()

	h := setupTestHub()
	h.jwksCache = jwk.NewCache(ctx)
	h.jwksURL = server.URL
	err = h.jwksCache.Register(h.jwksURL)
	require.NoError(t, err)

	t.Run("unexpected signing method", func(t *testing.T) {
		token := signRS512(t, priv, "kid-1", jwt.MapClaims{
			"sub": "user-rs",
			"exp": time.Now().Add(time.Hour).Unix(),
		})
		_, err := h.validateRS256(ctx, token)
		require.Error(t, err)
		assert.Contains(t, err.Error(), "invalid RS256 token")
	})

	t.Run("sub is not a string rejected", func(t *testing.T) {
		token := signRS256(t, priv, "kid-1", jwt.MapClaims{
			"sub": 12345, // integer instead of string
			"exp": time.Now().Add(time.Hour).Unix(),
		})
		_, err := h.validateRS256(ctx, token)
		require.Error(t, err)
		assert.Contains(t, err.Error(), "invalid RS256 token")
	})
}

func TestHandleWebSocket_EdgeCases(t *testing.T) {
	t.Run("rate limited", func(t *testing.T) {
		h := setupTestHub()
		h.UpgradeLimiter.capacity = 0 // block all
		h.UpgradeLimiter.ratePerSec = 0

		rec := httptest.NewRecorder()
		req, err := http.NewRequest(http.MethodGet, "/ws?ticket=123", nil)
		require.NoError(t, err)

		cfg := &config.Config{}
		h.HandleWebSocket(rec, req, cfg)
		assert.Equal(t, http.StatusTooManyRequests, rec.Code)
	})

	t.Run("at capacity", func(t *testing.T) {
		h := hubWithTicketRedis(t, "user-123:jti-abc")
		h.maxClients = 1
		h.Clients["existing-client"] = &Client{}

		rec := httptest.NewRecorder()
		req, err := http.NewRequest(http.MethodGet, "/ws?ticket="+validTicket, nil)
		require.NoError(t, err)

		cfg := &config.Config{}
		h.HandleWebSocket(rec, req, cfg)
		assert.Equal(t, http.StatusServiceUnavailable, rec.Code)
	})

	t.Run("upgrade failed", func(t *testing.T) {
		h := hubWithTicketRedis(t, "user-123:jti-abc")

		rec := httptest.NewRecorder()
		// standard GET request is not a valid WebSocket upgrade request
		req, err := http.NewRequest(http.MethodGet, "/ws?ticket="+validTicket, nil)
		require.NoError(t, err)

		cfg := &config.Config{}
		h.HandleWebSocket(rec, req, cfg)
		// Gorilla upgrader returns 400 Bad Request if upgrade fails
		assert.Equal(t, http.StatusBadRequest, rec.Code)
	})
}
