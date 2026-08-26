package main

import (
	"crypto/rand"
	"crypto/rsa"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/asn1"
	"encoding/pem"
	"math/big"
	"net/http"
	"net/http/httptest"
	"net/url"
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

func writeGatewayMTLSMaterial(t *testing.T) (string, string, string, string) {
	t.Helper()
	now := time.Now()
	caKey, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)
	caTemplate := &x509.Certificate{
		SerialNumber:          big.NewInt(1),
		Subject:               pkix.Name{CommonName: "test-ca"},
		NotBefore:             now.Add(-time.Minute),
		NotAfter:              now.Add(time.Hour),
		IsCA:                  true,
		BasicConstraintsValid: true,
		KeyUsage:              x509.KeyUsageCertSign,
	}
	caDER, err := x509.CreateCertificate(rand.Reader, caTemplate, caTemplate, &caKey.PublicKey, caKey)
	require.NoError(t, err)
	caCertificate, err := x509.ParseCertificate(caDER)
	require.NoError(t, err)
	clientKey, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)
	identity := "spiffe://university.ecosystem/ns/university-ecosystem/sa/gateway"
	identityURI, err := url.Parse(identity)
	require.NoError(t, err)
	clientTemplate := &x509.Certificate{SerialNumber: big.NewInt(2), Subject: pkix.Name{CommonName: "gateway-client"}, NotBefore: now.Add(-time.Minute), NotAfter: now.Add(time.Hour), KeyUsage: x509.KeyUsageDigitalSignature, ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth}, URIs: []*url.URL{identityURI}}
	clientDER, err := x509.CreateCertificate(rand.Reader, clientTemplate, caCertificate, &clientKey.PublicKey, caKey)
	require.NoError(t, err)
	directory := t.TempDir()
	caPath := directory + string(os.PathSeparator) + "ca.crt"
	certPath := directory + string(os.PathSeparator) + "client.crt"
	keyPath := directory + string(os.PathSeparator) + "client.key"
	require.NoError(t, os.WriteFile(caPath, pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: caDER}), 0o600))
	require.NoError(t, os.WriteFile(certPath, pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: clientDER}), 0o600))
	require.NoError(t, os.WriteFile(keyPath, pem.EncodeToMemory(&pem.Block{Type: "RSA PRIVATE KEY", Bytes: x509.MarshalPKCS1PrivateKey(clientKey)}), 0o600))
	return caPath, certPath, keyPath, identity
}

func TestConventionalGRPCClientCredentials(t *testing.T) {
	caPath, certPath, keyPath, identity := writeGatewayMTLSMaterial(t)
	cfg := &config.Config{
		GRPCCAFile:            caPath,
		GRPCClientCertFile:    certPath,
		GRPCClientKeyFile:     keyPath,
		GRPCServerName:        "file-processor.example.test",
		GRPCClientIdentityURI: identity,
	}

	tlsConfig, err := conventionalGRPCClientTLSConfig(cfg)
	require.NoError(t, err)
	assert.Equal(t, "file-processor.example.test", tlsConfig.ServerName)

	credentials, err := conventionalGRPCClientCredentials(cfg)
	require.NoError(t, err)
	require.NotNil(t, credentials)
	connection, client, err := initGRPC(&config.Config{
		FileProcessorAddr:     "localhost:50051",
		GrpcUseTLS:            true,
		GRPCCAFile:            caPath,
		GRPCClientCertFile:    certPath,
		GRPCClientKeyFile:     keyPath,
		GRPCServerName:        "file-processor.example.test",
		GRPCClientIdentityURI: identity,
	}, initLogger())
	require.NoError(t, err)
	require.NotNil(t, client)
	require.NoError(t, connection.Close())

	t.Run("invalid CA", func(t *testing.T) {
		invalidCA := t.TempDir() + string(os.PathSeparator) + "ca.crt"
		require.NoError(t, os.WriteFile(invalidCA, []byte("not a certificate"), 0o600))
		_, err := conventionalGRPCClientCredentials(&config.Config{GRPCCAFile: invalidCA})
		assert.ErrorContains(t, err, "parse gRPC client CA")
	})

	t.Run("invalid client keypair", func(t *testing.T) {
		invalidCert := t.TempDir() + string(os.PathSeparator) + "client.crt"
		invalidKey := t.TempDir() + string(os.PathSeparator) + "client.key"
		require.NoError(t, os.WriteFile(invalidCert, []byte("not a certificate"), 0o600))
		require.NoError(t, os.WriteFile(invalidKey, []byte("not a key"), 0o600))
		_, err := conventionalGRPCClientCredentials(&config.Config{GRPCCAFile: caPath, GRPCClientCertFile: invalidCert, GRPCClientKeyFile: invalidKey})
		assert.ErrorContains(t, err, "load gRPC client certificate")
	})

	t.Run("invalid client leaf contract", func(t *testing.T) {
		badKey, keyErr := rsa.GenerateKey(rand.Reader, 2048)
		require.NoError(t, keyErr)
		badTemplate := &x509.Certificate{SerialNumber: big.NewInt(99), Subject: pkix.Name{CommonName: "not-a-client"}, NotBefore: time.Now().Add(-time.Minute), NotAfter: time.Now().Add(time.Hour), KeyUsage: x509.KeyUsageDigitalSignature, ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth}}
		badDER, createErr := x509.CreateCertificate(rand.Reader, badTemplate, badTemplate, &badKey.PublicKey, badKey)
		require.NoError(t, createErr)
		badCertPath := t.TempDir() + string(os.PathSeparator) + "client.crt"
		badKeyPath := t.TempDir() + string(os.PathSeparator) + "client.key"
		require.NoError(t, os.WriteFile(badCertPath, pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: badDER}), 0o600))
		require.NoError(t, os.WriteFile(badKeyPath, pem.EncodeToMemory(&pem.Block{Type: "RSA PRIVATE KEY", Bytes: x509.MarshalPKCS1PrivateKey(badKey)}), 0o600))
		_, credentialErr := conventionalGRPCClientCredentials(&config.Config{GRPCCAFile: caPath, GRPCClientCertFile: badCertPath, GRPCClientKeyFile: badKeyPath, GRPCClientIdentityURI: identity})
		require.ErrorContains(t, credentialErr, "clientAuth-only")
	})
}

func TestValidateConventionalClientCertificate(t *testing.T) {
	now := time.Now()
	identity := "spiffe://university.ecosystem/ns/university-ecosystem/sa/gateway"
	identityURI, err := url.Parse(identity)
	require.NoError(t, err)
	makeCertificate := func(t *testing.T, template x509.Certificate) tls.Certificate {
		t.Helper()
		key, err := rsa.GenerateKey(rand.Reader, 2048)
		require.NoError(t, err)
		der, err := x509.CreateCertificate(rand.Reader, &template, &template, &key.PublicKey, key)
		require.NoError(t, err)
		return tls.Certificate{Certificate: [][]byte{der}, PrivateKey: key}
	}
	validTemplate := x509.Certificate{SerialNumber: big.NewInt(10), Subject: pkix.Name{CommonName: "gateway"}, NotBefore: now.Add(-time.Minute), NotAfter: now.Add(time.Hour), KeyUsage: x509.KeyUsageDigitalSignature, ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth}, URIs: []*url.URL{identityURI}}
	require.NoError(t, validateConventionalClientCertificate(makeCertificate(t, validTemplate), identity, now))

	for name, mutate := range map[string]func(*x509.Certificate){
		"CA leaf": func(c *x509.Certificate) {
			c.IsCA = true
			c.BasicConstraintsValid = true
			c.KeyUsage = x509.KeyUsageCertSign
		},
		"expired":       func(c *x509.Certificate) { c.NotAfter = now.Add(-time.Second) },
		"not yet valid": func(c *x509.Certificate) { c.NotBefore = now.Add(time.Second) },
		"missing EKU":   func(c *x509.Certificate) { c.ExtKeyUsage = nil },
		"dual EKU": func(c *x509.Certificate) {
			c.ExtKeyUsage = []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth, x509.ExtKeyUsageServerAuth}
		},
		"any EKU":      func(c *x509.Certificate) { c.ExtKeyUsage = []x509.ExtKeyUsage{x509.ExtKeyUsageAny} },
		"unknown EKU":  func(c *x509.Certificate) { c.UnknownExtKeyUsage = []asn1.ObjectIdentifier{{1, 2, 3, 4}} },
		"missing URI":  func(c *x509.Certificate) { c.URIs = nil },
		"multiple URI": func(c *x509.Certificate) { c.URIs = []*url.URL{identityURI, identityURI} },
		"wrong URI": func(c *x509.Certificate) {
			other, parseErr := url.Parse("spiffe://university.ecosystem/ns/university-ecosystem/sa/other")
			require.NoError(t, parseErr)
			c.URIs = []*url.URL{other}
		},
	} {
		t.Run(name, func(t *testing.T) {
			template := validTemplate
			mutate(&template)
			require.Error(t, validateConventionalClientCertificate(makeCertificate(t, template), identity, now))
		})
	}

	t.Run("multiple leaf certificates", func(t *testing.T) {
		certificate := makeCertificate(t, validTemplate)
		certificate.Certificate = append(certificate.Certificate, certificate.Certificate[0])
		require.Error(t, validateConventionalClientCertificate(certificate, identity, now))
	})

	t.Run("malformed certificate", func(t *testing.T) {
		require.Error(t, validateConventionalClientCertificate(tls.Certificate{Certificate: [][]byte{[]byte("not-der")}}, identity, now))
	})

	t.Run("leaf after CA", func(t *testing.T) {
		caTemplate := validTemplate
		caTemplate.IsCA = true
		caTemplate.BasicConstraintsValid = true
		caTemplate.KeyUsage = x509.KeyUsageCertSign
		caCertificate := makeCertificate(t, caTemplate)
		leafCertificate := makeCertificate(t, validTemplate)
		leafCertificate.Certificate = append(caCertificate.Certificate, leafCertificate.Certificate...)
		require.Error(t, validateConventionalClientCertificate(leafCertificate, identity, now))
	})

	t.Run("invalid configured identity", func(t *testing.T) {
		require.Error(t, validateConventionalClientCertificate(makeCertificate(t, validTemplate), "https://example.test/gateway", now))
	})
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
