package hub

import (
	"context"
	"crypto/rand"
	"crypto/rsa"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/lestrrat-go/jwx/v2/jwk"
	"github.com/quic-go/webtransport-go"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/ws-hub/pkg/config"
)

func TestUpgradeOriginChecks_AllowOnlyExplicitOrigins(t *testing.T) {
	h := setupTestHub()
	wtServer := h.webTransportServer
	SetAllowedOrigins([]string{"https://allowed.example"})
	t.Cleanup(func() { SetAllowedOrigins(nil) })

	noOrigin := httptest.NewRequest(http.MethodGet, "/ws", nil)
	assert.True(t, upgrader.CheckOrigin(noOrigin))

	configured := httptest.NewRequest(http.MethodGet, "/ws", nil)
	configured.Header.Set("Origin", "https://allowed.example")
	assert.True(t, upgrader.CheckOrigin(configured))

	t.Setenv("WS_ALLOWED_ORIGINS", "https://env.example, https://second.example")
	fromEnv := httptest.NewRequest(http.MethodGet, "/ws", nil)
	fromEnv.Header.Set("Origin", "https://second.example")
	assert.True(t, upgrader.CheckOrigin(fromEnv))
	assert.True(t, wtServer.CheckOrigin(fromEnv))

	unknown := httptest.NewRequest(http.MethodGet, "/ws", nil)
	unknown.Header.Set("Origin", "https://blocked.example")
	assert.False(t, upgrader.CheckOrigin(unknown))

	assert.False(t, wtServer.CheckOrigin(unknown))

	t.Setenv("WS_ALLOWED_ORIGINS", "")
	assert.False(t, wtServer.CheckOrigin(unknown))
	configuredWT := httptest.NewRequest(http.MethodGet, "/wt", nil)
	configuredWT.Header.Set("Origin", "https://allowed.example")
	assert.True(t, wtServer.CheckOrigin(configuredWT))
}

func TestConfigureWebTransportServer_BindsSecureUpgradeServerToHTTP3Mux(t *testing.T) {
	SetAllowedOrigins([]string{"https://allowed.example"})
	t.Cleanup(func() { SetAllowedOrigins(nil) })
	h := setupTestHub()
	handler := http.NewServeMux()

	server := h.ConfigureWebTransportServer(":8443", handler)

	assert.Same(t, server, h.webTransportServer)
	require.NotNil(t, server.H3)
	assert.Equal(t, ":8443", server.H3.Addr)
	assert.Same(t, handler, server.H3.Handler)
	allowed := httptest.NewRequest(http.MethodGet, "/wt", nil)
	allowed.Header.Set("Origin", "https://allowed.example")
	assert.True(t, server.CheckOrigin(allowed))
	blocked := httptest.NewRequest(http.MethodGet, "/wt", nil)
	blocked.Header.Set("Origin", "https://blocked.example")
	assert.False(t, server.CheckOrigin(blocked))
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

func TestHandleWebTransport_SuccessRegistersCanonicalTicketIdentity(t *testing.T) {
	h := hubWithWTTicketRedis(t, "user-wt:jti-wt")
	h.Register = make(chan *Client, 1)
	oldValidate := validateUpgradeTicketFunc
	oldUpgrade := upgradeWTFunc
	oldSession := newWebTransportSessionFunc
	t.Cleanup(func() {
		validateUpgradeTicketFunc = oldValidate
		upgradeWTFunc = oldUpgrade
		newWebTransportSessionFunc = oldSession
	})
	validateUpgradeTicketFunc = func(*Hub, context.Context, string) (string, string, error) {
		return "user-wt", "tenant-wt", nil
	}
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
		assert.NotEmpty(t, client.ID)
		assert.NotEqual(t, client.UserID, client.ID)
		assert.Equal(t, "tenant-wt", client.Identity.TenantID)
		assert.Equal(t, "tenant-wt", client.ctx.Value(tenantIDKey))
		client.cancel()
	case <-time.After(time.Second):
		t.Fatal("successful WebTransport upgrade did not register a client")
	}
}

func TestNewConnectionID_IsUniqueAndNotUserDerived(t *testing.T) {
	first := newConnectionID()
	second := newConnectionID()

	assert.NotEmpty(t, first)
	assert.NotEqual(t, first, second)
	assert.NotEqual(t, "user-1", first)
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

func TestValidateRS256_RawKeyExtractionFailureIsRejected(t *testing.T) {
	priv, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)
	server := startJWKSServer(t, &priv.PublicKey, "kid-raw-error")

	h := setupTestHub()
	ctx := context.Background()
	require.NoError(t, h.SetupJWKS(ctx, server.URL))

	oldRaw := rawJWKFunc
	t.Cleanup(func() { rawJWKFunc = oldRaw })
	rawJWKFunc = func(jwk.Key, interface{}) error {
		return errors.New("raw key unavailable")
	}

	_, err = h.validateRS256(ctx, signRS256(t, priv, "kid-raw-error", jwt.MapClaims{
		"sub": "user-rs",
		"exp": time.Now().Add(time.Hour).Unix(),
	}))
	require.Error(t, err)
	assert.Contains(t, err.Error(), "invalid RS256 token")
}
