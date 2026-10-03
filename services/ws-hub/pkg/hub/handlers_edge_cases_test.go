// HTTP upgrade and transport-handler edge-case contracts.
package hub

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

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
	oldValidate := validateUpgradeTicketIdentityFunc
	t.Cleanup(func() { validateUpgradeTicketIdentityFunc = oldValidate })
	validateUpgradeTicketIdentityFunc = func(*Hub, context.Context, string) (upgradeTicketIdentity, error) {
		return upgradeTicketIdentity{}, nil
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
	runCtx, cancelRun := context.WithCancel(context.Background())
	runDone := make(chan struct{})
	go func() {
		h.Run(runCtx)
		close(runDone)
	}()
	require.Eventually(t, func() bool { return hubLifecycleContext(h) != nil }, time.Second, time.Millisecond)
	t.Cleanup(func() {
		h.Stop()
		cancelRun()
		select {
		case <-runDone:
		case <-time.After(time.Second):
			t.Error("hub run loop did not stop")
		}
	})
	oldValidate := validateUpgradeTicketIdentityFunc
	oldUpgrade := upgradeWTFunc
	oldSession := newWebTransportSessionFunc
	t.Cleanup(func() {
		validateUpgradeTicketIdentityFunc = oldValidate
		upgradeWTFunc = oldUpgrade
		newWebTransportSessionFunc = oldSession
	})
	validateUpgradeTicketIdentityFunc = func(*Hub, context.Context, string) (upgradeTicketIdentity, error) {
		return upgradeTicketIdentity{UserID: "user-wt", TenantID: "tenant-wt", SessionJTI: "22222222-2222-4222-8222-222222222222", SessionExpiresAt: time.Unix(9999999999, 0)}, nil
	}
	assert.NotNil(t, newWebTransportSessionFunc(nil))
	upgradeWTFunc = func(*webtransport.Server, http.ResponseWriter, *http.Request) (*webtransport.Session, error) {
		return nil, nil
	}
	newWebTransportSessionFunc = func(*webtransport.Session) Session { return newBlockingShutdownSession() }

	cfg := &config.Config{MaxClients: 100, SendBufferSize: 4}
	req := httptest.NewRequest(http.MethodGet, "/wt?ticket="+validWTTicket, nil)
	rec := httptest.NewRecorder()
	h.HandleWebTransport(rec, req, cfg)

	var client *Client
	require.Eventually(t, func() bool {
		h.mu.RLock()
		defer h.mu.RUnlock()
		for _, candidate := range h.Clients {
			if candidate.UserID == "user-wt" {
				client = candidate
				return true
			}
		}
		return false
	}, time.Second, time.Millisecond, "successful WebTransport upgrade did not register a client")
	if client == nil {
		t.Fatal("successful WebTransport upgrade registered a nil client")
	}
	{
		assert.Equal(t, "user-wt", client.UserID)
		assert.NotEmpty(t, client.ID)
		assert.NotEqual(t, client.UserID, client.ID)
		assert.Equal(t, "tenant-wt", client.Identity.TenantID)
		assert.Equal(t, "tenant-wt", client.ctx.Value(tenantIDKey))
		assert.Equal(t, "22222222-2222-4222-8222-222222222222", client.SessionJTI)
		assert.Equal(t, time.Unix(9999999999, 0), client.SessionExpiresAt)
	}
}

func TestNewConnectionID_IsUniqueAndNotUserDerived(t *testing.T) {
	first := newConnectionID()
	second := newConnectionID()

	assert.NotEmpty(t, first)
	assert.NotEqual(t, first, second)
	assert.NotEqual(t, "user-1", first)
}

func TestTryForceRefreshJWKS_RespectsCooldown(t *testing.T) {
	previous := _lastJWKSForceRefreshUnix.Load()
	t.Cleanup(func() { _lastJWKSForceRefreshUnix.Store(previous) })
	_lastJWKSForceRefreshUnix.Store(time.Now().Unix())
	h := setupTestHub()
	h.jwksURL = "http://127.0.0.1:1/jwks"
	assert.NotPanics(t, func() { h.tryForceRefreshJWKS(context.Background()) })
}
