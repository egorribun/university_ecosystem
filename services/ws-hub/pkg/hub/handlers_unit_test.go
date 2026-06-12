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
