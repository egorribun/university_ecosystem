package middleware

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strconv"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/go-redis/redis_rate/v10"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/require"
)

// proxyRedisCommands replaces only the command transport. It supplies deterministic
// per-key results, not Redis Lua/GCRA, refill timing, or distributed semantics.
// There is deliberately no embedded Redis client or possible network dial path.
type proxyRedisCommands struct {
	t    *testing.T
	keys []string
	used map[string]int
	fail bool
}

func (f *proxyRedisCommands) EvalSha(ctx context.Context, sha string, keys []string, args ...interface{}) *redis.Cmd {
	f.t.Helper()
	require.NotEmpty(f.t, sha)
	require.Len(f.t, keys, 1)
	// redis_rate v10.0.1 AllowN sends burst, rate, period in seconds, tokens.
	require.Equal(f.t, []interface{}{2, 7, float64(1), 1}, args)
	_, hasDeadline := ctx.Deadline()
	require.True(f.t, hasDeadline, "the Redis operation must retain its deadline")
	f.keys = append(f.keys, keys[0])
	if f.fail {
		return redis.NewCmdResult(nil, errors.New("synthetic script failure"))
	}
	f.used[keys[0]]++
	if f.used[keys[0]] > 2 {
		return redis.NewCmdResult([]interface{}{int64(0), int64(0), "2", "4"}, nil)
	}
	return redis.NewCmdResult([]interface{}{int64(1), int64(2 - f.used[keys[0]]), "-1", "4"}, nil)
}

func (f *proxyRedisCommands) Eval(context.Context, string, []string, ...interface{}) *redis.Cmd {
	f.t.Fatal("unexpected Eval command")
	return nil
}

func (f *proxyRedisCommands) EvalRO(context.Context, string, []string, ...interface{}) *redis.Cmd {
	f.t.Fatal("unexpected EvalRO command")
	return nil
}

func (f *proxyRedisCommands) EvalShaRO(context.Context, string, []string, ...interface{}) *redis.Cmd {
	f.t.Fatal("unexpected EvalShaRO command")
	return nil
}

func (f *proxyRedisCommands) ScriptExists(context.Context, ...string) *redis.BoolSliceCmd {
	f.t.Fatal("unexpected ScriptExists command")
	return nil
}

func (f *proxyRedisCommands) ScriptLoad(context.Context, string) *redis.StringCmd {
	f.t.Fatal("unexpected ScriptLoad command")
	return nil
}

func (f *proxyRedisCommands) Del(context.Context, ...string) *redis.IntCmd {
	f.t.Fatal("unexpected Del command")
	return nil
}

func newProxyRedisRouter(t *testing.T, fail bool) (*gin.Engine, *RateLimiter, *proxyRedisCommands) {
	t.Helper()
	commands := &proxyRedisCommands{t: t, used: make(map[string]int), fail: fail}
	limiter := NewFallbackRateLimiter()
	limiter.limiter = redis_rate.NewLimiter(commands)
	limiter.rps, limiter.burst = 7, 2
	t.Cleanup(func() { require.NoError(t, limiter.Close()) })
	router := gin.New()
	require.NoError(t, router.SetTrustedProxies([]string{"10.0.0.0/8"}))
	router.Use(limiter.Middleware(t.Context()))
	router.GET("/limited", func(c *gin.Context) { c.Status(http.StatusNoContent) })
	return router, limiter, commands
}

func proxyRedisRequest(t *testing.T, router *gin.Engine, peer string, forwarded []string, realIP string) *httptest.ResponseRecorder {
	t.Helper()
	request := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/limited", nil)
	request.RemoteAddr = peer
	for _, value := range forwarded {
		request.Header.Add("X-Forwarded-For", value)
	}
	if realIP != "" {
		request.Header.Set("X-Real-IP", realIP)
	}
	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, request)
	return recorder
}

func requireProxyRedisResponse(t *testing.T, recorder *httptest.ResponseRecorder, status, remaining int, before time.Time) {
	t.Helper()
	require.Equal(t, status, recorder.Code)
	require.Equal(t, "7", recorder.Header().Get("RateLimit-Limit"))
	require.Equal(t, "7;w=1", recorder.Header().Get("RateLimit-Policy"))
	require.Equal(t, strconv.Itoa(remaining), recorder.Header().Get("RateLimit-Remaining"))
	reset, err := strconv.ParseInt(recorder.Header().Get("RateLimit-Reset"), 10, 64)
	require.NoError(t, err)
	require.GreaterOrEqual(t, reset, before.Add(4*time.Second).Unix())
	require.LessOrEqual(t, reset, time.Now().Add(4*time.Second).Unix())
	if status == http.StatusTooManyRequests {
		require.Equal(t, "2", recorder.Header().Get("Retry-After"))
		require.JSONEq(t, `{"error":"rate limit exceeded","retry_after":2}`, recorder.Body.String())
	} else {
		require.Empty(t, recorder.Header().Get("Retry-After"))
	}
}

// A peer-key regression would merge A and B; trusting a forged leftmost value
// would let A escape its exhausted bucket. Both must affect real HTTP outcomes.
func TestRateLimiter_TrustedProxyRedis_ClientIsolation(t *testing.T) {
	router, limiter, commands := newProxyRedisRouter(t, false)
	steps := []struct {
		forwarded []string
		key       string
		status    int
		remaining int
	}{
		{[]string{"198.51.100.10, 10.0.0.2"}, "rate:ip:198.51.100.10", 204, 1},
		{[]string{"198.51.100.10, 10.0.0.2"}, "rate:ip:198.51.100.10", 204, 0},
		{[]string{"198.51.100.10, 10.0.0.2"}, "rate:ip:198.51.100.10", 429, 0},
		{[]string{"198.51.100.20, 10.0.0.2"}, "rate:ip:198.51.100.20", 204, 1},
		{[]string{"203.0.113.90, 198.51.100.10, 10.0.0.2"}, "rate:ip:198.51.100.10", 429, 0},
		// Gin v1.12 joins repeated fields; the rightmost untrusted client wins.
		{[]string{"203.0.113.91", "198.51.100.10, 10.0.0.2"}, "rate:ip:198.51.100.10", 429, 0},
	}
	var wantKeys []string
	for _, step := range steps {
		before := time.Now()
		recorder := proxyRedisRequest(t, router, "10.0.0.1:1234", step.forwarded, "")
		requireProxyRedisResponse(t, recorder, step.status, step.remaining, before)
		wantKeys = append(wantKeys, step.key)
		require.Equal(t, wantKeys, commands.keys)
	}
	require.Empty(t, limiter.fallbackCounters, "successful commands must not silently use fallback")
}

func TestRateLimiter_TrustedProxyRedis_UntrustedAndMalformed(t *testing.T) {
	for _, tc := range []struct {
		name string
		peer string
		key  string
		xff  [][]string
		real []string
	}{
		{"untrusted peer", "192.0.2.8:1234", "rate:ip:192.0.2.8", [][]string{{"198.51.100.1"}, {"198.51.100.2"}, {"198.51.100.3"}}, []string{"203.0.113.1", "203.0.113.2", "203.0.113.3"}},
		// Invalid rightmost hop invalidates XFF; absent X-Real-IP leaves the peer.
		{"malformed chain", "10.0.0.1:1234", "rate:ip:10.0.0.1", [][]string{{"198.51.100.1, invalid"}, {"198.51.100.2, invalid"}, {"198.51.100.3, invalid"}}, []string{"", "", ""}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			router, limiter, commands := newProxyRedisRouter(t, false)
			for i := range tc.xff {
				status, remaining := http.StatusNoContent, 1-i
				if i == 2 {
					status, remaining = http.StatusTooManyRequests, 0
				}
				before := time.Now()
				recorder := proxyRedisRequest(t, router, tc.peer, tc.xff[i], tc.real[i])
				requireProxyRedisResponse(t, recorder, status, remaining, before)
			}
			require.Equal(t, []string{tc.key, tc.key, tc.key}, commands.keys)
			require.Empty(t, limiter.fallbackCounters)
		})
	}
}

func TestRateLimiter_TrustedProxyRedis_ScriptErrorUsesBoundedFallback(t *testing.T) {
	router, limiter, commands := newProxyRedisRouter(t, true)
	limiter.fallbackMaxEntries = 1
	// Keep the existing three-request budget; pin the stored window after the
	// first request so this control cannot expire during this control.
	for i := 0; i < 4; i++ {
		recorder := proxyRedisRequest(t, router, "10.0.0.1:1234", []string{"198.51.100.10"}, "")
		if i < 3 {
			require.Equal(t, http.StatusNoContent, recorder.Code)
		} else {
			require.Equal(t, http.StatusTooManyRequests, recorder.Code)
			require.Equal(t, "60", recorder.Header().Get("Retry-After"))
			require.JSONEq(t, `{"error":"rate_limit_exceeded","retry_after":60}`, recorder.Body.String())
		}
		require.Empty(t, recorder.Header().Get("RateLimit-Limit"))
		if i == 0 {
			limiter.fallbackMu.Lock()
			entry, exists := limiter.fallbackCounters["ip:198.51.100.10"]
			if !exists || entry == nil {
				limiter.fallbackMu.Unlock()
				t.Fatal("successful fallback request must create a non-nil client counter")
				return
			}
			entry.windowStart = time.Now().Add(time.Hour).Unix()
			limiter.fallbackMu.Unlock()
		}
	}
	recorder := proxyRedisRequest(t, router, "10.0.0.1:1234", []string{"198.51.100.20"}, "")
	require.Equal(t, http.StatusTooManyRequests, recorder.Code, "a new key must fail closed at capacity")
	require.Len(t, limiter.fallbackCounters, 1)
	require.Equal(t, []string{"rate:ip:198.51.100.10", "rate:ip:198.51.100.10", "rate:ip:198.51.100.10", "rate:ip:198.51.100.10", "rate:ip:198.51.100.20"}, commands.keys)
}
