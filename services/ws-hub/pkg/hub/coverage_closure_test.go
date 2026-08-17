package hub

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"testing"
	"time"

	lru "github.com/hashicorp/golang-lru/v2"
	"github.com/lestrrat-go/jwx/v2/jwk"
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
		func() { NewInternalAPIAuthClient("http://auth.test", nil) },
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
	registerJWKSFunc = func(*jwk.Cache, string, ...jwk.RegisterOption) error {
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
