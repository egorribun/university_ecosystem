package hub

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/lestrrat-go/jwx/v2/jwk"
	"github.com/quic-go/webtransport-go"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/ws-hub/pkg/config"
)

func TestUpgradeOriginChecks_AllowConfiguredEnvironmentAndRejectProductionUnknown(t *testing.T) {
	SetAllowedOrigins([]string{"https://allowed.example"})
	t.Cleanup(func() { SetAllowedOrigins(nil) })
	t.Setenv("ENVIRONMENT", "production")

	noOrigin := httptest.NewRequest(http.MethodGet, "/ws", nil)
	assert.True(t, upgrader.CheckOrigin(noOrigin))

	configured := httptest.NewRequest(http.MethodGet, "/ws", nil)
	configured.Header.Set("Origin", "https://allowed.example")
	assert.True(t, upgrader.CheckOrigin(configured))

	t.Setenv("WS_ALLOWED_ORIGINS", "https://env.example, https://second.example")
	fromEnv := httptest.NewRequest(http.MethodGet, "/ws", nil)
	fromEnv.Header.Set("Origin", "https://second.example")
	assert.True(t, upgrader.CheckOrigin(fromEnv))
	assert.True(t, wtUpgrader.CheckOrigin(fromEnv))

	unknown := httptest.NewRequest(http.MethodGet, "/ws", nil)
	unknown.Header.Set("Origin", "https://blocked.example")
	assert.False(t, upgrader.CheckOrigin(unknown))

	t.Setenv("ENVIRONMENT", "development")
	assert.True(t, upgrader.CheckOrigin(unknown))
	assert.True(t, wtUpgrader.CheckOrigin(unknown))

	t.Setenv("ENVIRONMENT", "production")
	t.Setenv("WS_ALLOWED_ORIGINS", "")
	assert.False(t, wtUpgrader.CheckOrigin(unknown))
	configuredWT := httptest.NewRequest(http.MethodGet, "/wt", nil)
	configuredWT.Header.Set("Origin", "https://allowed.example")
	assert.True(t, wtUpgrader.CheckOrigin(configuredWT))
}

func TestUpgradeHandlers_RejectEmptyValidatedUser(t *testing.T) {
	h := setupTestHub()
	oldValidate := validateUpgradeTicketFunc
	t.Cleanup(func() { validateUpgradeTicketFunc = oldValidate })
	validateUpgradeTicketFunc = func(*Hub, context.Context, string) (string, string, error) {
		return "", "", nil
	}
	cfg := &config.Config{MaxClients: 100}

	wsResponse := httptest.NewRecorder()
	h.HandleWebSocket(wsResponse, httptest.NewRequest(http.MethodGet, "/ws?ticket="+validWTTicket, nil), cfg)
	assert.Equal(t, http.StatusUnauthorized, wsResponse.Code)

	wtResponse := httptest.NewRecorder()
	h.HandleWebTransport(wtResponse, httptest.NewRequest(http.MethodGet, "/wt?ticket="+validWTTicket, nil), cfg)
	assert.Equal(t, http.StatusUnauthorized, wtResponse.Code)
}

func TestHandleWebTransport_SuccessRegistersTenantIdentity(t *testing.T) {
	h := hubWithWTTicketRedis(t, "user-wt:jti-wt:tenant-wt")
	h.Register = make(chan *Client, 1)
	oldUpgrade := upgradeWTFunc
	oldSession := newWebTransportSessionFunc
	t.Cleanup(func() {
		upgradeWTFunc = oldUpgrade
		newWebTransportSessionFunc = oldSession
	})
	assert.NotNil(t, newWebTransportSessionFunc(nil))
	upgradeWTFunc = func(*webtransport.Server, http.ResponseWriter, *http.Request) (*webtransport.Session, error) {
		return nil, nil
	}
	newWebTransportSessionFunc = func(*webtransport.Session) Session { return &recordingSession{} }

	cfg := &config.Config{MaxClients: 100, SendBufferSize: 4}
	req := httptest.NewRequest(http.MethodGet, "/wt?ticket="+validWTTicket, nil)
	rec := httptest.NewRecorder()
	h.HandleWebTransport(rec, req, cfg)

	select {
	case client := <-h.Register:
		assert.Equal(t, "user-wt", client.UserID)
		assert.Equal(t, "tenant-wt", client.Identity.TenantID)
		client.cancel()
	case <-time.After(time.Second):
		t.Fatal("successful WebTransport upgrade did not register a client")
	}
}

func TestValidateRS256_JWKSFetchFailureIsReturned(t *testing.T) {
	h := setupTestHub()
	ctx := context.Background()
	h.jwksCache = jwk.NewCache(ctx)
	h.jwksURL = "http://127.0.0.1:1/jwks"
	require.NoError(t, h.jwksCache.Register(h.jwksURL))

	_, err := h.validateRS256(ctx, "eyJhbGciOiJSUzI1NiJ9.e30.signature")
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to fetch")
}

func TestTryForceRefreshJWKS_RespectsCooldown(t *testing.T) {
	previous := _lastJWKSForceRefreshUnix.Load()
	t.Cleanup(func() { _lastJWKSForceRefreshUnix.Store(previous) })
	_lastJWKSForceRefreshUnix.Store(time.Now().Unix())
	h := setupTestHub()
	h.jwksURL = "http://127.0.0.1:1/jwks"
	assert.NotPanics(t, func() { h.tryForceRefreshJWKS(context.Background()) })
}
