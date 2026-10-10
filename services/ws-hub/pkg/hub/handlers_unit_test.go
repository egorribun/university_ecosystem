package hub

// Coverage tests (testing session 9) for the WebSocket upgrade path:
// validateUpgradeTicketIdentity (mock RESP server — idiom ported from
// services/cmd/uni-cli/main_test.go) and the full HandleWebSocket upgrade →
// join → broadcast → deliver E2E flow with a real gorilla/websocket dial.
//
// Client-to-hub frames are limited to join/leave; chat mutations are never
// relayed from the socket, so these tests need no NATS connection.

import (
	"context"
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/gorilla/websocket"
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
func respondTicketRESP(write func(string), upper, getdelReply, existsReply string) {
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
	case strings.Contains(upper, "EXISTS"):
		write(existsReply)
	default:
		write("+OK\r\n")
	}
}

// handleTicketConn serves one mock-Redis connection until it closes.
func handleTicketConn(c net.Conn, getdelReply, existsReply string) {
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
			respondTicketRESP(write, strings.ToUpper(part), getdelReply, existsReply)
		}
	}
}

func startTicketRESPServer(t *testing.T, getdelReply, existsReply string) string {
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
			go handleTicketConn(conn, getdelReply, existsReply)
		}
	}()
	return ln.Addr().String()
}

func hubWithTicketRedis(t *testing.T, getdelReply string) *Hub {
	t.Helper()
	return hubWithTicketRedisReplies(t, getdelReply, ":0\r\n")
}

func hubWithTicketRedisReplies(t *testing.T, getdelReply, existsReply string) *Hub {
	t.Helper()
	addr := startTicketRESPServer(t, getdelReply, existsReply)
	h := setupTestHub()
	h.redisClient = goredis.NewClient(&goredis.Options{Addr: addr})
	h.revocationRedisClient = h.redisClient
	t.Cleanup(func() { _ = h.redisClient.Close() }) //nolint:errcheck // test cleanup
	return h
}

const validTicket = "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff" // pragma: allowlist secret
const validSessionJTI = "11111111-1111-4111-8111-111111111111"

// ---------------------------------------------------------------------------
// validateUpgradeTicketIdentity
// ---------------------------------------------------------------------------

func TestValidateUpgradeTicketIdentity_NoRedisConfigured(t *testing.T) {
	h := setupTestHub() // redisClient nil
	_, err := h.validateUpgradeTicketIdentity(context.Background(), validTicket)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "redis not available")
}

func TestValidateUpgradeTicketIdentity_RejectsBadFormat(t *testing.T) {
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
			_, err := h.validateUpgradeTicketIdentity(context.Background(), tc.ticket)
			require.Error(t, err)
			assert.Contains(t, err.Error(), tc.errSub)
		})
	}
}

func TestValidateUpgradeTicketIdentity_NotFound(t *testing.T) {
	h := hubWithTicketRedis(t, "") // GETDEL → nil
	_, err := h.validateUpgradeTicketIdentity(context.Background(), validTicket)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "not found or already used")
}

func TestValidateUpgradeTicketIdentity_MalformedPayloads(t *testing.T) {
	cases := []struct {
		name  string
		reply string
	}{
		{"no colon", "user-without-jti"},
		{"empty user", ":jti-only"},
		{"empty jti", "user-id:"},
		{"unexpected tenant segment", "user-id:jti:tenant-id"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			h := hubWithTicketRedis(t, tc.reply)
			_, err := h.validateUpgradeTicketIdentity(context.Background(), validTicket)
			require.Error(t, err)
			assert.Contains(t, err.Error(), "malformed ticket payload")
		})
	}
}

func TestValidateUpgradeTicketIdentity_HappyPath(t *testing.T) {
	h := hubWithTicketRedis(t, "user-77:"+validSessionJTI+":9999999999")
	identity, err := h.validateUpgradeTicketIdentity(context.Background(), validTicket)
	require.NoError(t, err)
	assert.Equal(t, "user-77", identity.UserID)
}

func TestValidateUpgradeTicketIdentityRetainsSessionJTI(t *testing.T) {
	h := hubWithTicketRedis(t, "user-77:"+validSessionJTI+":9999999999")
	identity, err := h.validateUpgradeTicketIdentity(context.Background(), validTicket)
	require.NoError(t, err)
	assert.Equal(t, "user-77", identity.UserID)
	assert.Equal(t, validSessionJTI, identity.SessionJTI)
	assert.Equal(t, time.Unix(9999999999, 0), identity.SessionExpiresAt)
	assert.Empty(t, identity.TenantID)
}

func TestValidateUpgradeTicketIdentityRejectsMalformedSessionJTI(t *testing.T) {
	h := hubWithTicketRedis(t, "user-77:not-a-uuid:9999999999")

	_, err := h.validateUpgradeTicketIdentity(context.Background(), validTicket)

	require.Error(t, err)
	assert.Contains(t, err.Error(), "invalid session JTI")
}

func TestValidateUpgradeTicketIdentityRejectsNonCanonicalSessionJTI(t *testing.T) {
	// Redis keys and the revocation Pub/Sub payload are byte-identity based.
	// An upper-case (although parseable) UUID would not match a canonical
	// lower-case publisher, so ticket acceptance must reject it fail-closed.
	h := hubWithTicketRedis(t, "user-77:AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA:9999999999")

	_, err := h.validateUpgradeTicketIdentity(context.Background(), validTicket)

	require.Error(t, err)
	assert.Contains(t, err.Error(), "invalid session JTI")
}

func TestValidateUpgradeTicketIdentity_RejectsRevokedJTI(t *testing.T) {
	mr := miniredis.RunT(t)
	redisClient := goredis.NewClient(&goredis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { require.NoError(t, redisClient.Close()) })
	h := setupTestHub()
	h.redisClient = redisClient
	h.revocationRedisClient = redisClient

	require.NoError(t, mr.Set(wsTicketKeyPrefix+validTicket, "user-77:"+validSessionJTI+":9999999999"))
	require.NoError(t, mr.Set("revoked:jti:"+validSessionJTI, "1"))

	_, err := h.validateUpgradeTicketIdentity(context.Background(), validTicket)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "ticket session is revoked")
	assert.False(t, mr.Exists(wsTicketKeyPrefix+validTicket), "revoked ticket must remain single-use")
}

func TestValidateUpgradeTicketIdentity_UsesDedicatedRevocationStore(t *testing.T) {
	ticketStore := miniredis.RunT(t)
	revocationStore := miniredis.RunT(t)
	ticketClient := goredis.NewClient(&goredis.Options{Addr: ticketStore.Addr()})
	revocationClient := goredis.NewClient(&goredis.Options{Addr: revocationStore.Addr()})
	t.Cleanup(func() {
		require.NoError(t, ticketClient.Close())
		require.NoError(t, revocationClient.Close())
	})
	h := NewHub(nil, newTestLogger(), nil, &config.Config{}, ticketClient, revocationClient)
	t.Cleanup(h.Stop)

	require.NoError(t, ticketStore.Set(wsTicketKeyPrefix+validTicket, "user-77:"+validSessionJTI+":9999999999"))
	require.NoError(t, revocationStore.Set("revoked:jti:"+validSessionJTI, "1"))

	_, err := h.validateUpgradeTicketIdentity(context.Background(), validTicket)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "ticket session is revoked")
}

func TestValidateUpgradeTicketIdentity_FailsClosedWhenRevocationLookupFails(t *testing.T) {
	h := hubWithTicketRedisReplies(t, "user-77:"+validSessionJTI+":9999999999", "-ERR revocation lookup failed\r\n")

	_, err := h.validateUpgradeTicketIdentity(context.Background(), validTicket)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "session revocation check failed")
}

func TestValidateUpgradeTicketIdentity_RequiresDedicatedRevocationStore(t *testing.T) {
	mr := miniredis.RunT(t)
	ticketClient := goredis.NewClient(&goredis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { require.NoError(t, ticketClient.Close()) })
	require.NoError(t, mr.Set(wsTicketKeyPrefix+validTicket, "user-77:"+validSessionJTI+":9999999999"))
	h := NewHub(nil, newTestLogger(), nil, &config.Config{}, ticketClient, nil)
	t.Cleanup(h.Stop)

	_, err := h.validateUpgradeTicketIdentity(context.Background(), validTicket)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "revocation redis not available")
}

// ---------------------------------------------------------------------------
// JWKS setup
// ---------------------------------------------------------------------------

func TestSetupJWKS_EmptyURLIsNoop(t *testing.T) {
	h := setupTestHub()
	require.NoError(t, h.SetupJWKS(context.Background(), ""))
	assert.False(t, h.HasJWKSCache())
}

// ---------------------------------------------------------------------------
// HandleWebSocket — full upgrade → join → broadcast → deliver E2E
// ---------------------------------------------------------------------------

func TestHandleWebSocket_E2EUpgradeJoinAndDeliver(t *testing.T) {
	h := hubWithTicketRedis(t, "user-e2e:"+validSessionJTI+":9999999999")
	cfg := &config.Config{SendBufferSize: 8}
	oldValidate := validateUpgradeTicketIdentityFunc
	t.Cleanup(func() { validateUpgradeTicketIdentityFunc = oldValidate })
	validateUpgradeTicketIdentityFunc = func(*Hub, context.Context, string) (upgradeTicketIdentity, error) {
		return upgradeTicketIdentity{UserID: "user-e2e", TenantID: "tenant-e2e", SessionJTI: "11111111-1111-4111-8111-111111111111", SessionExpiresAt: time.Unix(9999999999, 0)}, nil
	}

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

	// Registered under a connection-scoped id while retaining canonical user identity.
	var client *Client
	var connectionID string
	require.Eventually(t, func() bool {
		h.mu.RLock()
		defer h.mu.RUnlock()
		for id, candidate := range h.Clients {
			if candidate.UserID == "user-e2e" {
				client = candidate
				connectionID = id
				return id != candidate.UserID
			}
		}
		return false
	}, 2*time.Second, 10*time.Millisecond)
	require.NotNil(t, client)
	require.NotNil(t, client.Identity)
	assert.Equal(t, "tenant-e2e", client.Identity.TenantID)
	assert.Equal(t, "tenant-e2e", client.ctx.Value(tenantIDKey))
	assert.NotEmpty(t, client.SessionJTI)
	assert.Equal(t, time.Unix(9999999999, 0), client.SessionExpiresAt)

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
		_, ok := h.Clients[connectionID]
		return !ok
	}, 2*time.Second, 10*time.Millisecond)
}

func TestHandleWebSocket_RejectsDisallowedOrigin(t *testing.T) {
	origEnv := os.Getenv("ENVIRONMENT")
	require.NoError(t, os.Setenv("ENVIRONMENT", "production"))
	defer func() { require.NoError(t, os.Setenv("ENVIRONMENT", origEnv)) }()

	SetAllowedOrigins([]string{"http://allowed.example"})
	defer SetAllowedOrigins(nil)

	h := hubWithTicketRedis(t, "user-origin:"+validSessionJTI+":9999999999")
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
	if resp == nil {
		t.Fatal("expected non-nil response")
	}
	defer func() { _ = resp.Body.Close() }() //nolint:errcheck // test cleanup
	assert.Equal(t, http.StatusUnauthorized, resp.StatusCode)
}

func TestHandleWebSocket_EdgeCases(t *testing.T) {
	t.Run("rate limited", func(t *testing.T) {
		h := setupTestHub()
		h.UpgradeLimiter.capacity = 0 // block all
		h.UpgradeLimiter.ratePerSec = 0

		rec := httptest.NewRecorder()
		req, err := http.NewRequestWithContext(t.Context(), http.MethodGet, "/ws?ticket=123", nil)
		require.NoError(t, err)

		cfg := &config.Config{}
		h.HandleWebSocket(rec, req, cfg)
		assert.Equal(t, http.StatusTooManyRequests, rec.Code)
	})

	t.Run("at capacity", func(t *testing.T) {
		h := hubWithTicketRedis(t, "user-123:"+validSessionJTI+":9999999999")
		h.maxClients = 1
		h.Clients["existing-client"] = &Client{}

		rec := httptest.NewRecorder()
		req, err := http.NewRequestWithContext(t.Context(), http.MethodGet, "/ws?ticket="+validTicket, nil)
		require.NoError(t, err)

		cfg := &config.Config{}
		h.HandleWebSocket(rec, req, cfg)
		assert.Equal(t, http.StatusServiceUnavailable, rec.Code)
	})

	t.Run("upgrade failed", func(t *testing.T) {
		h := hubWithTicketRedis(t, "user-123:"+validSessionJTI+":9999999999")

		rec := httptest.NewRecorder()
		// standard GET request is not a valid WebSocket upgrade request
		req, err := http.NewRequestWithContext(t.Context(), http.MethodGet, "/ws?ticket="+validTicket, nil)
		require.NoError(t, err)

		cfg := &config.Config{}
		h.HandleWebSocket(rec, req, cfg)
		// Gorilla upgrader returns 400 Bad Request if upgrade fails
		assert.Equal(t, http.StatusBadRequest, rec.Code)
	})
}
