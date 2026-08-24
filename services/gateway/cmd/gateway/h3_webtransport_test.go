package main

import (
	"crypto/rand"
	"crypto/rsa"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"math/big"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/university-ecosystem/gateway/internal/config"
	"github.com/university-ecosystem/gateway/middleware"
)

func generateUnitTestJWT(t *testing.T, secret []byte, userID, role, jti string) string {
	t.Helper()
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
		"sub":       userID,
		"aud":       middleware.DefaultJWTAudience,
		"role":      role,
		"jti":       jti,
		"is_active": true,
		"iat":       time.Now().Unix(),
		"exp":       time.Now().Add(1 * time.Hour).Unix(),
	})
	tokenStr, err := token.SignedString(secret)
	require.NoError(t, err)
	return tokenStr
}

func TestGateway_AltSvcHeaderAndWSWebTransportRoutes(t *testing.T) {
	redisServer := miniredis.RunT(t)
	const testJWTSecret = "my-secret-key-that-is-at-least-32-chars-long" // #nosec G101 // pragma: allowlist secret

	// 1. Mock ws-hub backend server
	capturedHeaders := make(http.Header)
	wsHubServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		for k, v := range r.Header {
			capturedHeaders[k] = v
		}
		if strings.HasPrefix(r.URL.Path, "/ws") || r.URL.Path == "/webtransport" {
			w.WriteHeader(http.StatusOK)
			//nolint:errcheck
			_, _ = w.Write([]byte("ws-hub response"))
			return
		}
		http.Error(w, "Not found", http.StatusNotFound)
	}))
	defer wsHubServer.Close()

	// 2. Gateway config with H3 enabled
	cfg := &config.Config{
		Port:               "8080",
		BackendURL:         wsHubServer.URL,
		WsHubURL:           wsHubServer.URL,
		RedisURL:           "redis://" + redisServer.Addr() + "/3",
		RevocationRedisURL: "redis://" + redisServer.Addr() + "/0",
		JWTSecret:          testJWTSecret,
		InternalHMACSecret: "test-internal-secret",
		H3Enabled:          true,
		H3Port:             "8443",
		H3AltSvcMaxAge:     2592000,
		AllowedOrigins:     []string{"*"},
		Environment:        "testing",
	}

	logger := initLogger()
	router, err := setupRouter(cfg, logger, nil, nil, t.Context())
	require.NoError(t, err)
	gatewayServer := httptest.NewServer(router)
	defer gatewayServer.Close()

	// 3. Test Alt-Svc header on /health endpoint
	reqHealth, err := http.NewRequestWithContext(t.Context(), http.MethodGet, gatewayServer.URL+"/health", nil)
	require.NoError(t, err)
	resp, err := http.DefaultClient.Do(reqHealth)
	require.NoError(t, err)
	require.NotNil(t, resp)
	defer func() { assert.NoError(t, resp.Body.Close()) }()

	assert.Equal(t, http.StatusOK, resp.StatusCode)
	assert.Equal(t, `h3=":8443"; ma=2592000`, resp.Header.Get("Alt-Svc"))

	// 4. Test proxying /ws route to ws-hub
	req, err := http.NewRequestWithContext(t.Context(), http.MethodGet, gatewayServer.URL+"/ws?ticket=test-ticket-123", nil)
	require.NoError(t, err)

	resp, err = http.DefaultClient.Do(req)
	require.NoError(t, err)
	require.NotNil(t, resp)
	defer func() { assert.NoError(t, resp.Body.Close()) }()

	assert.Equal(t, http.StatusOK, resp.StatusCode)

	// 5. Test proxying /webtransport route to ws-hub
	req, err = http.NewRequestWithContext(t.Context(), http.MethodGet, gatewayServer.URL+"/webtransport?ticket=test-ticket-456", nil)
	require.NoError(t, err)

	resp, err = http.DefaultClient.Do(req)
	require.NoError(t, err)
	require.NotNil(t, resp)
	defer func() { assert.NoError(t, resp.Body.Close()) }()

	assert.Equal(t, http.StatusOK, resp.StatusCode)
}

func TestPrepareTLSConfig_SelfSignedGeneration(t *testing.T) {
	cfg := &config.Config{
		TLSCertFile: "",
		TLSKeyFile:  "",
	}
	logger := initLogger()

	tlsCfg, err := prepareTLSConfig(cfg, logger)
	require.NoError(t, err)
	require.NotNil(t, tlsCfg)
	assert.Len(t, tlsCfg.Certificates, 1)
}

func TestPrepareTLSConfig_LoadsCertificateFiles(t *testing.T) {
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)
	certificateDER, err := x509.CreateCertificate(rand.Reader, &x509.Certificate{
		SerialNumber: big.NewInt(1),
		Subject:      pkix.Name{CommonName: "gateway-test"},
		NotBefore:    time.Now().Add(-time.Minute),
		NotAfter:     time.Now().Add(time.Hour),
		KeyUsage:     x509.KeyUsageDigitalSignature | x509.KeyUsageKeyEncipherment,
		ExtKeyUsage:  []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
	}, &x509.Certificate{
		SerialNumber: big.NewInt(1),
		Subject:      pkix.Name{CommonName: "gateway-test"},
		NotBefore:    time.Now().Add(-time.Minute),
		NotAfter:     time.Now().Add(time.Hour),
		KeyUsage:     x509.KeyUsageDigitalSignature | x509.KeyUsageKeyEncipherment,
		ExtKeyUsage:  []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
	}, &key.PublicKey, key)
	require.NoError(t, err)

	certPath := t.TempDir() + string(os.PathSeparator) + "gateway.crt"
	keyPath := t.TempDir() + string(os.PathSeparator) + "gateway.key"
	require.NoError(t, os.WriteFile(certPath, pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: certificateDER}), 0o600))
	require.NoError(t, os.WriteFile(keyPath, pem.EncodeToMemory(&pem.Block{Type: "RSA PRIVATE KEY", Bytes: x509.MarshalPKCS1PrivateKey(key)}), 0o600))

	tlsCfg, err := prepareTLSConfig(&config.Config{TLSCertFile: certPath, TLSKeyFile: keyPath}, initLogger())
	require.NoError(t, err)
	require.NotNil(t, tlsCfg)
	assert.Equal(t, uint16(tls.VersionTLS13), tlsCfg.MinVersion)
	assert.Len(t, tlsCfg.Certificates, 1)
}

func TestPrepareTLSConfig_RejectsInvalidCertificateFiles(t *testing.T) {
	certPath := t.TempDir() + string(os.PathSeparator) + "gateway.crt"
	keyPath := t.TempDir() + string(os.PathSeparator) + "gateway.key"
	require.NoError(t, os.WriteFile(certPath, []byte("not-a-certificate"), 0o600))
	require.NoError(t, os.WriteFile(keyPath, []byte("not-a-key"), 0o600))

	tlsCfg, err := prepareTLSConfig(&config.Config{TLSCertFile: certPath, TLSKeyFile: keyPath}, initLogger())
	assert.Nil(t, tlsCfg)
	assert.Error(t, err)
}

func TestRunServer_H3PreparationAndShutdown(t *testing.T) {
	t.Run("h3 tls preparation failure does not prevent http shutdown", func(t *testing.T) {
		certPath := t.TempDir() + string(os.PathSeparator) + "gateway.crt"
		keyPath := t.TempDir() + string(os.PathSeparator) + "gateway.key"
		require.NoError(t, os.WriteFile(certPath, []byte("not-a-certificate"), 0o600))
		require.NoError(t, os.WriteFile(keyPath, []byte("not-a-key"), 0o600))

		cfg := &config.Config{
			Port:        "-1",
			H3Enabled:   true,
			H3Port:      "0",
			TLSCertFile: certPath,
			TLSKeyFile:  keyPath,
		}

		err := runServer(cfg, gin.New(), initLogger())
		assert.Error(t, err)
	})
}

func TestGenerateTestJWT_Helpers(t *testing.T) {
	secret := []byte("secret-key-at-least-32-chars-long")
	tokenStr := generateUnitTestJWT(t, secret, "user-123", "student", "jti-456")
	require.NotEmpty(t, tokenStr)

	parsed, err := jwt.Parse(tokenStr, func(token *jwt.Token) (interface{}, error) {
		return secret, nil
	})
	require.NoError(t, err)
	assert.True(t, parsed.Valid)
}
