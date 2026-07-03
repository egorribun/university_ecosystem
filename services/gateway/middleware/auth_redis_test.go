package middleware

// Coverage tests (testing session 9) for the Redis-backed session-revocation
// paths that the existing auth_test.go cannot reach because it constructs the
// middleware with a nil *redis.Client (every revocation check then early-returns
// "valid" via the m.redis == nil guard).
//
// These tests point a REAL go-redis client at a hand-rolled mock RESP server
// (the respondRESP idiom from services/cmd/uni-cli/main_test.go) so that
// verifySession / checkSessionInRedis / checkL1Cache / WarmL1Cache execute for
// real. The integration tier (//go:build integration, testcontainers) covers
// the live-Redis pub/sub path; these unit tests stay dependency-free.
//
// ⚠ XFetch trap: checkL1Cache calls shouldRefreshProbabilistic, which returns a
// spurious "miss" ~37% of the time even for a fresh entry. WarmL1Cache results
// are therefore asserted via the raw m.l1cache.Get (deterministic), never via
// checkL1Cache.

import (
	"context"
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// mockRedisConfig configures the canned replies of the mock RESP server.
type mockRedisConfig struct {
	existsReply string   // ":1\r\n" (revoked) or ":0\r\n" (not revoked)
	scanKeys    []string // keys returned by a single-page SCAN (cursor "0")
	scanErr     bool     // reply "-ERR" to SCAN to exercise the warmup skip path
}

// respondGatewayRESP writes a canned RESP reply for the uppercased request
// fragment, covering the commands the gateway middleware exercises.
func respondGatewayRESP(write func(string), upper string, cfg mockRedisConfig) {
	switch {
	case strings.Contains(upper, "HELLO"):
		write("-ERR unknown command 'HELLO'\r\n") // force RESP2 fallback
	case strings.Contains(upper, "CLIENT"):
		write("-ERR unknown command 'CLIENT'\r\n")
	case strings.Contains(upper, "PING"):
		write("+PONG\r\n")
	case strings.Contains(upper, "EXISTS"):
		reply := cfg.existsReply
		if reply == "" {
			reply = ":0\r\n"
		}
		write(reply)
	case strings.Contains(upper, "SCAN"):
		if cfg.scanErr {
			write("-ERR scan failed\r\n")
			return
		}
		var b strings.Builder
		// SCAN reply: 2-element array [cursor-string, keys-array]. Cursor "0" ends iteration.
		b.WriteString("*2\r\n$1\r\n0\r\n")
		fmt.Fprintf(&b, "*%d\r\n", len(cfg.scanKeys))
		for _, k := range cfg.scanKeys {
			fmt.Fprintf(&b, "$%d\r\n%s\r\n", len(k), k)
		}
		write(b.String())
	default:
		write("+OK\r\n")
	}
}

// startMockRedis spins up a loopback RESP server and returns its redis:// URL
// plus a cleanup func. No external dependency.
//
// The cleanup func closes BOTH the listener AND every accepted connection — a
// connection-pooling client (go-redis) keeps a warm socket, so closing only the
// listener would leave that socket fully serving. Closing the conns forces the
// pooled socket to error and the redial to hit a closed listener (refused),
// which is what genuinely simulates a Redis outage.
func startMockRedis(t *testing.T, cfg mockRedisConfig) (string, func()) {
	t.Helper()
	var lc net.ListenConfig
	ln, err := lc.Listen(context.Background(), "tcp", "127.0.0.1:0")
	require.NoError(t, err)

	var mu sync.Mutex
	var conns []net.Conn

	go func() {
		for {
			conn, err := ln.Accept()
			if err != nil {
				return
			}
			mu.Lock()
			conns = append(conns, conn)
			mu.Unlock()
			go func(c net.Conn) {
				defer func() { _ = c.Close() }()                      //nolint:errcheck // mock cleanup
				write := func(s string) { _, _ = c.Write([]byte(s)) } //nolint:errcheck // best-effort write
				buf := make([]byte, 4096)
				for {
					n, err := c.Read(buf)
					if err != nil {
						return
					}
					for _, part := range strings.Split(string(buf[:n]), "*") {
						if part == "" {
							continue
						}
						respondGatewayRESP(write, strings.ToUpper(part), cfg)
					}
				}
			}(conn)
		}
	}()

	return fmt.Sprintf("redis://%s", ln.Addr().String()), func() {
		_ = ln.Close() //nolint:errcheck // cleanup
		mu.Lock()
		for _, c := range conns {
			_ = c.Close() //nolint:errcheck // cleanup
		}
		mu.Unlock()
	}
}

// newRedisMiddleware builds a JWTMiddleware whose *redis.Client is connected to
// the given mock URL, with the connection pre-warmed so the 50ms timeout in
// checkSessionInRedis covers only the command round-trip (not the RESP2
// handshake).
func newRedisMiddleware(t *testing.T, url string) *JWTMiddleware {
	t.Helper()
	opt, err := redis.ParseURL(url)
	require.NoError(t, err)
	client := redis.NewClient(opt)
	_ = client.Ping(context.Background()).Err() //nolint:errcheck // warm the pool; HELLO -ERR RESP2 fallback is expected mock noise
	t.Cleanup(func() { _ = client.Close() })    //nolint:errcheck // cleanup
	return NewJWTMiddleware(testSecret, client)
}

func revocableClaims(jti string) Claims {
	return Claims{
		RegisteredClaims: jwt.RegisteredClaims{
			ID:        jti,
			IssuedAt:  jwt.NewNumericDate(time.Now().Add(-1 * time.Minute)),
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(1 * time.Hour)),
		},
		UserID:   "user-1",
		Role:     "student",
		IsActive: true,
	}
}

func bearerRequest(t *testing.T, token string) *http.Request {
	t.Helper()
	req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	return req
}

// ---------------------------------------------------------------------------
// Validate — revocation paths through real Redis
// ---------------------------------------------------------------------------

func TestValidate_RevokedSessionRejected(t *testing.T) {
	url, stop := startMockRedis(t, mockRedisConfig{existsReply: ":1\r\n"}) // jti is revoked
	defer stop()
	m := newRedisMiddleware(t, url)
	router := createTestRouter(m.Validate(context.Background()))

	token := createValidToken(testSecret, revocableClaims("jti-revoked"))
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, bearerRequest(t, token))

	assert.Equal(t, http.StatusUnauthorized, rec.Code)
	assert.Contains(t, rec.Body.String(), "session expired or revoked")
}

func TestValidate_ActiveSessionPasses(t *testing.T) {
	url, stop := startMockRedis(t, mockRedisConfig{existsReply: ":0\r\n"}) // not revoked
	defer stop()
	m := newRedisMiddleware(t, url)

	handlerCalled := false
	router := gin.New()
	router.GET("/test", m.Validate(context.Background()), func(c *gin.Context) {
		handlerCalled = true
		c.Status(http.StatusOK)
	})

	token := createValidToken(testSecret, revocableClaims("jti-active"))
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, bearerRequest(t, token))

	assert.Equal(t, http.StatusOK, rec.Code)
	assert.True(t, handlerCalled, "downstream handler must run for a valid, non-revoked session")
}

func TestValidate_MissingJTIRejected(t *testing.T) {
	url, stop := startMockRedis(t, mockRedisConfig{existsReply: ":0\r\n"})
	defer stop()
	m := newRedisMiddleware(t, url)
	router := createTestRouter(m.Validate(context.Background()))

	// FIX-JTI-01: a token without a jti cannot be correlated with a session →
	// treated as invalid even though signature + iat + exp are all fine.
	claims := revocableClaims("")
	token := createValidToken(testSecret, claims)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, bearerRequest(t, token))

	assert.Equal(t, http.StatusUnauthorized, rec.Code)
}

func TestValidate_RedisDownFailsSecure(t *testing.T) {
	url, stop := startMockRedis(t, mockRedisConfig{existsReply: ":0\r\n"})
	m := newRedisMiddleware(t, url)
	stop() // kill the server BEFORE the request → checkSessionInRedis errors

	router := createTestRouter(m.Validate(context.Background()))
	token := createValidToken(testSecret, revocableClaims("jti-x"))
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, bearerRequest(t, token))

	// GW-P1-03: Validate uses failSecure=true → Redis outage → 503, never a pass.
	assert.Equal(t, http.StatusServiceUnavailable, rec.Code)
	assert.Contains(t, rec.Body.String(), "session verification temporarily unavailable")
}

func TestValidate_CookieTokenExtraction(t *testing.T) {
	url, stop := startMockRedis(t, mockRedisConfig{existsReply: ":0\r\n"})
	defer stop()
	m := newRedisMiddleware(t, url)

	handlerCalled := false
	router := gin.New()
	router.GET("/test", m.Validate(context.Background()), func(c *gin.Context) {
		handlerCalled = true
		c.Status(http.StatusOK)
	})

	token := createValidToken(testSecret, revocableClaims("jti-cookie"))
	req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
	req.AddCookie(&http.Cookie{Name: AccessTokenCookieName, Value: token}) //nolint:gosec // G124: test-only cookie, Secure/HttpOnly not applicable in unit tests
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusOK, rec.Code)
	assert.True(t, handlerCalled, "Validate must read the access_token_v2 cookie when no Authorization header is present")
}

// ---------------------------------------------------------------------------
// Optional — revocation paths
// ---------------------------------------------------------------------------

func TestOptional_RevokedSessionContinuesUnauthenticated(t *testing.T) {
	url, stop := startMockRedis(t, mockRedisConfig{existsReply: ":1\r\n"}) // revoked
	defer stop()
	m := newRedisMiddleware(t, url)

	var sawUserID bool
	router := gin.New()
	router.GET("/test", m.Optional(context.Background()), func(c *gin.Context) {
		_, sawUserID = c.Get("user_id")
		c.Status(http.StatusOK)
	})

	token := createValidToken(testSecret, revocableClaims("jti-revoked"))
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, bearerRequest(t, token))

	assert.Equal(t, http.StatusOK, rec.Code)
	assert.False(t, sawUserID, "Optional must NOT set user context for a revoked session (continues unauthenticated)")
}

func TestOptional_RedisDownFailsOpenUnauthenticated(t *testing.T) {
	url, stop := startMockRedis(t, mockRedisConfig{existsReply: ":0\r\n"})
	m := newRedisMiddleware(t, url)
	stop() // Redis down

	var sawUserID bool
	router := gin.New()
	router.GET("/test", m.Optional(context.Background()), func(c *gin.Context) {
		_, sawUserID = c.Get("user_id")
		c.Status(http.StatusOK)
	})
	token := createValidToken(testSecret, revocableClaims("jti-x"))
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, bearerRequest(t, token))

	// GW-P1-03 fail-open: Optional() passes failSecure=false to verifySession, so a
	// Redis error yields (isValid=false, shouldDeny=false) → the request continues
	// as UNAUTHENTICATED (200, no user context). It never treats a possibly-revoked
	// token as valid, and the 503 branch is unreachable for the optional path.
	assert.Equal(t, http.StatusOK, rec.Code)
	assert.False(t, sawUserID, "a Redis outage must not authenticate the request on the optional path")
}

// ---------------------------------------------------------------------------
// WarmL1Cache + ListenForRevocations
// ---------------------------------------------------------------------------

func TestWarmL1Cache_PopulatesFromScan(t *testing.T) {
	keys := []string{"revoked:jti:aaa", "revoked:jti:bbb"}
	url, stop := startMockRedis(t, mockRedisConfig{scanKeys: keys})
	defer stop()
	m := newRedisMiddleware(t, url)

	m.WarmL1Cache(context.Background())

	for _, k := range keys {
		// Assert via the raw LRU (NOT checkL1Cache) to dodge the XFetch flake.
		entry, ok := m.l1cache.Get(k)
		require.True(t, ok, "WarmL1Cache should have seeded %s", k)
		assert.True(t, entry.exists, "warmed revocation entries are marked exists=true")
	}
}

func TestWarmL1Cache_ScanErrorSkips(t *testing.T) {
	url, stop := startMockRedis(t, mockRedisConfig{scanErr: true})
	defer stop()
	m := newRedisMiddleware(t, url)

	m.WarmL1Cache(context.Background()) // must return without panicking
	assert.Equal(t, 0, m.l1cache.Len(), "a SCAN error must leave the L1 cache empty")
}

func TestWarmL1Cache_NilRedisNoop(t *testing.T) {
	m := NewJWTMiddleware(testSecret, nil)
	assert.NotPanics(t, func() { m.WarmL1Cache(context.Background()) })
}

func TestListenForRevocations_NilRedisNoop(t *testing.T) {
	m := NewJWTMiddleware(testSecret, nil)
	assert.NotPanics(t, func() { m.ListenForRevocations(context.Background()) })
}
