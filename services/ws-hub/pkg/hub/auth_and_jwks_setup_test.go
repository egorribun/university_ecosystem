// Internal-auth construction and JWKS setup failure contracts.
package hub

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	lru "github.com/hashicorp/golang-lru/v2"
	"github.com/lestrrat-go/httprc/v3"
	"github.com/lestrrat-go/jwx/v3/jwk"
	"github.com/nats-io/nats.go"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestNewInternalAPIAuthClient_FailsFastWhenCacheConstructionFails(t *testing.T) {
	old := newAuthLRUFunc
	t.Cleanup(func() { newAuthLRUFunc = old })
	newAuthLRUFunc = func(int) (*lru.Cache[string, cacheEntry], error) {
		return nil, errors.New("synthetic auth cache failure")
	}

	assert.PanicsWithValue(
		t,
		"failed to initialize LRU cache: synthetic auth cache failure",
		func() { NewInternalAPIAuthClientWithToken("http://auth.test", "", nil) },
	)
}

func TestNewHub_FailsFastWhenDedupCacheConstructionFails(t *testing.T) {
	old := newDedupLRUFunc
	t.Cleanup(func() { newDedupLRUFunc = old })
	newDedupLRUFunc = func(int) (*lru.Cache[string, time.Time], error) {
		return nil, errors.New("synthetic dedup cache failure")
	}

	assert.PanicsWithValue(
		t,
		"failed to initialize dedup LRU cache: synthetic dedup cache failure",
		func() { NewHub(nil, slog.New(slog.NewTextHandler(io.Discard, nil)), nil, nil, nil) },
	)
}

func TestNewHub_RejectsMultipleRevocationRedisClients(t *testing.T) {
	assert.PanicsWithValue(
		t,
		"ws-hub: at most one revocation Redis client may be configured",
		func() {
			NewHub(
				nil,
				slog.New(slog.NewTextHandler(io.Discard, nil)),
				nil,
				nil,
				nil,
				nil,
				nil,
			)
		},
	)
}

func TestSetupJWKS_PropagatesRegistrationFailure(t *testing.T) {
	old := registerJWKSFunc
	t.Cleanup(func() { registerJWKSFunc = old })
	wantErr := errors.New("synthetic JWKS registration failure")
	registerJWKSFunc = func(context.Context, *jwk.Cache, string, ...jwk.RegisterOption) error {
		return wantErr
	}
	h := NewHub(nil, slog.New(slog.NewTextHandler(io.Discard, nil)), nil, nil, nil)
	t.Cleanup(h.Stop)

	err := h.SetupJWKS(context.Background(), "https://auth.test/.well-known/jwks.json")

	require.Error(t, err)
	assert.ErrorIs(t, err, wantErr)
}

func TestDefaultNATSUnsubscribeAdapterDelegates(t *testing.T) {
	err := unsubscribePullFunc(&nats.Subscription{})

	require.Error(t, err)
}

func newTestJWKSCache(t *testing.T, h *Hub, ctx context.Context, configuredURL string) *jwk.Cache {
	t.Helper()
	client := httprc.NewClient(httprc.WithWhitelist(jwk.NewMapWhitelist().Add(configuredURL)))
	cacheCtx, cancel := context.WithCancel(ctx)
	cache, err := jwk.NewCache(cacheCtx, client)
	require.NoError(t, err)
	h.jwksMu.Lock()
	h.jwksCache = cache
	h.jwksCacheCtx = cacheCtx
	h.jwksCacheCancel = cancel
	h.jwksURL = configuredURL
	h.jwksMu.Unlock()
	t.Cleanup(func() {
		h.jwksMu.Lock()
		defer h.jwksMu.Unlock()
		if h.jwksCache == cache {
			h.closeJWKSCacheLocked(context.Background())
		} else {
			// Setup or Hub.Stop already removed and shut down this cache.
			cancel()
		}
	})
	return cache
}

func TestJWKSCacheRejectsUnconfiguredURL(t *testing.T) {
	h := NewHub(nil, slog.New(slog.NewTextHandler(io.Discard, nil)), nil, nil, nil)
	t.Cleanup(h.Stop)
	configuredURL := "https://auth.test/.well-known/jwks.json"
	cache := newTestJWKSCache(t, h, context.Background(), configuredURL)

	err := cache.Register(
		context.Background(),
		"https://attacker.test/.well-known/jwks.json",
		jwk.WithWaitReady(false),
	)
	require.ErrorIs(t, err, httprc.ErrBlockedByWhitelist())
}

func TestCloseJWKSCacheBoundsShutdownAndCancelsParentBeforeError(t *testing.T) {
	old := shutdownJWKSCacheFunc
	t.Cleanup(func() { shutdownJWKSCacheFunc = old })
	wantErr := errors.New("synthetic shutdown timeout")
	parentCanceled := false
	shutdownJWKSCacheFunc = func(ctx context.Context, _ *jwk.Cache) error {
		assert.True(t, parentCanceled, "cache lifetime must be canceled before joining workers")
		deadline, ok := ctx.Deadline()
		require.True(t, ok)
		remaining := time.Until(deadline)
		assert.Greater(t, remaining, 4*time.Second)
		assert.LessOrEqual(t, remaining, jwksCacheShutdownTimeout)
		return wantErr
	}

	h := NewHub(nil, slog.New(slog.NewTextHandler(io.Discard, nil)), nil, nil, nil)
	t.Cleanup(h.Stop)
	h.jwksCache = &jwk.Cache{}
	h.jwksCacheCancel = func() { parentCanceled = true }

	h.jwksMu.Lock()
	h.closeJWKSCacheLocked(context.Background())
	h.jwksMu.Unlock()

	assert.True(t, parentCanceled)
	assert.Nil(t, h.jwksCache)
	assert.Nil(t, h.jwksCacheCancel)
}

func TestRefreshJWKSCallerCancellationStopsFetch(t *testing.T) {
	requestStarted := make(chan struct{})
	requestCanceled := make(chan struct{})
	var startedOnce, canceledOnce sync.Once
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		startedOnce.Do(func() { close(requestStarted) })
		<-r.Context().Done()
		canceledOnce.Do(func() { close(requestCanceled) })
	}))
	t.Cleanup(server.Close)

	h := NewHub(nil, slog.New(slog.NewTextHandler(io.Discard, nil)), nil, nil, nil)
	t.Cleanup(h.Stop)
	cache := newTestJWKSCache(t, h, context.Background(), server.URL)
	require.NoError(t, cache.Register(context.Background(), server.URL, jwk.WithWaitReady(false)))
	requestCtx, cancelRequest := context.WithCancel(context.Background())
	t.Cleanup(cancelRequest)
	refreshDone := make(chan error, 1)
	go func() { refreshDone <- h.refreshJWKS(requestCtx) }()
	select {
	case <-requestStarted:
	case <-time.After(2 * time.Second):
		t.Fatal("JWKS fetch did not start")
	}

	cancelRequest()
	select {
	case <-refreshDone:
	case <-time.After(2 * time.Second):
		t.Fatal("caller JWKS refresh did not return after request cancellation")
	}
	assert.True(t, h.HasJWKSCache(), "a canceled caller must not shut down the shared cache")

	// The cache owns the shared fetch worker, so caller cancellation only ends
	// this synchronous wait. Hub shutdown owns cancellation of the HTTP fetch.
	h.Stop()
	select {
	case <-requestCanceled:
	case <-time.After(2 * time.Second):
		t.Fatal("cache shutdown did not cancel the shared JWKS fetch")
	}
}

func TestSetupJWKSHTTPClientTimeoutCancelsFetch(t *testing.T) {
	requestStarted := make(chan struct{})
	requestCanceled := make(chan struct{})
	var startedOnce, canceledOnce sync.Once
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		startedOnce.Do(func() { close(requestStarted) })
		<-r.Context().Done()
		canceledOnce.Do(func() { close(requestCanceled) })
	}))
	t.Cleanup(server.Close)

	h := NewHub(nil, slog.New(slog.NewTextHandler(io.Discard, nil)), nil, nil, nil)
	t.Cleanup(h.Stop)
	setupDone := make(chan error, 1)
	go func() { setupDone <- h.SetupJWKS(context.Background(), server.URL) }()
	select {
	case <-requestStarted:
	case <-time.After(2 * time.Second):
		t.Fatal("JWKS fetch did not start")
	}

	select {
	case <-requestCanceled:
	case <-time.After(jwksRefreshTimeout + 2*time.Second):
		t.Fatal("JWKS HTTP client timeout did not cancel the stalled request")
	}
	select {
	case err := <-setupDone:
		require.NoError(t, err, "JWKS setup remains fail-open after a timed-out initial fetch")
	case <-time.After(2 * time.Second):
		t.Fatal("JWKS setup remained blocked after its HTTP request timed out")
	}
	assert.True(t, h.HasJWKSCache(), "a timed-out refresh must leave the cache available for recovery")
}

func TestCloseJWKSCacheCancelsInFlightFetch(t *testing.T) {
	requestStarted := make(chan struct{})
	requestCanceled := make(chan struct{})
	var startedOnce, canceledOnce sync.Once
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		startedOnce.Do(func() { close(requestStarted) })
		<-r.Context().Done()
		canceledOnce.Do(func() { close(requestCanceled) })
	}))
	t.Cleanup(server.Close)

	h := NewHub(nil, slog.New(slog.NewTextHandler(io.Discard, nil)), nil, nil, nil)
	t.Cleanup(h.Stop)
	cache := newTestJWKSCache(t, h, context.Background(), server.URL)
	require.NoError(t, cache.Register(context.Background(), server.URL, jwk.WithWaitReady(false)))
	// The production wrapper must bind a background caller to both cache
	// lifetime and the refresh deadline instead of relying on httprc to cancel
	// an unrelated caller context during Shutdown.
	refreshDone := make(chan error, 1)
	go func() { refreshDone <- h.refreshJWKS(context.Background()) }()
	select {
	case <-requestStarted:
	case <-time.After(2 * time.Second):
		t.Fatal("JWKS fetch did not start")
	}

	stopDone := make(chan struct{})
	go func() {
		h.Stop()
		close(stopDone)
	}()
	select {
	case <-requestCanceled:
	case <-time.After(2 * time.Second):
		t.Fatal("JWKS fetch request was not canceled by cache shutdown")
	}
	select {
	case <-refreshDone:
	case <-time.After(2 * time.Second):
		t.Fatal("in-flight application JWKS refresh did not return after shutdown")
	}
	select {
	case <-stopDone:
	case <-time.After(2 * time.Second):
		t.Fatal("Hub.Stop did not finish after canceling the JWKS refresh")
	}
	assert.Nil(t, h.jwksCache)
	assert.Nil(t, h.jwksCacheCtx)
	assert.Nil(t, h.jwksCacheCancel)
	assert.NotNil(t, cache)
}
