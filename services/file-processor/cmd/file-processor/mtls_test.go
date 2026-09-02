package main

import (
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"math/big"
	"net"
	"net/url"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/file-processor/internal/config"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/health/grpc_health_v1"
)

type testMTLSMaterial struct {
	caFile            string
	serverCertFile    string
	serverKeyFile     string
	serverCert        tls.Certificate
	clientCert        tls.Certificate
	probeCert         tls.Certificate
	noURICert         tls.Certificate
	wrongIdentityCert tls.Certificate
	multiURICert      tls.Certificate
	dualEKUCert       tls.Certificate
	caClientCert      tls.Certificate
	wrongClientCert   tls.Certificate
	serverName        string
	allowedURIs       []string
}

func writeTestMTLSMaterial(t *testing.T) testMTLSMaterial {
	t.Helper()
	directory := t.TempDir()
	serverName := "file-processor.university-ecosystem.svc"
	gatewayURI := "spiffe://university.ecosystem/ns/university-ecosystem/sa/gateway"
	probeURI := "spiffe://university.ecosystem/ns/university-ecosystem/sa/file-processor-probe"
	caCert, caKey, caPEM := issueTestCA(t, "trusted-ca")
	wrongCACert, wrongCAKey, _ := issueTestCA(t, "wrong-ca")
	serverCertPEM, serverKeyPEM, serverCert := issueTestLeaf(t, caCert, caKey, "server", []string{serverName}, nil, []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth})
	clientCertPEM, clientKeyPEM, clientCert := issueTestLeaf(t, caCert, caKey, "gateway", nil, []string{gatewayURI}, []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth})
	_, _, probeCert := issueTestLeaf(t, caCert, caKey, "probe", nil, []string{probeURI}, []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth})
	_, _, noURICert := issueTestLeaf(t, caCert, caKey, "no-uri", nil, nil, []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth})
	_, _, wrongIdentityCert := issueTestLeaf(t, caCert, caKey, "wrong-identity", nil, []string{"spiffe://university.ecosystem/ns/university-ecosystem/sa/other"}, []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth})
	_, _, multiURICert := issueTestLeaf(t, caCert, caKey, "multi-uri", nil, []string{gatewayURI, "spiffe://university.ecosystem/ns/university-ecosystem/sa/other"}, []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth})
	_, _, dualEKUCert := issueTestLeaf(t, caCert, caKey, "dual-eku", nil, []string{probeURI}, []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth, x509.ExtKeyUsageServerAuth})
	caClientCert := issueTestClientCA(t, caCert, caKey, gatewayURI)
	wrongCertPEM, wrongKeyPEM, wrongClientCert := issueTestLeaf(t, wrongCACert, wrongCAKey, "wrong-client", nil, []string{gatewayURI}, []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth})
	_ = clientCertPEM
	_ = clientKeyPEM
	_ = wrongCertPEM
	_ = wrongKeyPEM
	caFile := filepath.Join(directory, "ca.crt")
	serverCertFile := filepath.Join(directory, "tls.crt")
	serverKeyFile := filepath.Join(directory, "tls.key")
	require.NoError(t, os.WriteFile(caFile, caPEM, 0o600))
	require.NoError(t, os.WriteFile(serverCertFile, serverCertPEM, 0o600))
	require.NoError(t, os.WriteFile(serverKeyFile, serverKeyPEM, 0o600))
	return testMTLSMaterial{caFile: caFile, serverCertFile: serverCertFile, serverKeyFile: serverKeyFile, serverCert: serverCert, clientCert: clientCert, probeCert: probeCert, noURICert: noURICert, wrongIdentityCert: wrongIdentityCert, multiURICert: multiURICert, dualEKUCert: dualEKUCert, caClientCert: caClientCert, wrongClientCert: wrongClientCert, serverName: serverName, allowedURIs: []string{gatewayURI, probeURI}}
}

func issueTestClientCA(t *testing.T, parent *x509.Certificate, parentKey *ecdsa.PrivateKey, identity string) tls.Certificate {
	t.Helper()
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	require.NoError(t, err)
	identityURI, err := url.Parse(identity)
	require.NoError(t, err)
	template := &x509.Certificate{SerialNumber: big.NewInt(time.Now().UnixNano()), Subject: pkix.Name{CommonName: "client-ca"}, NotBefore: time.Now().Add(-time.Minute), NotAfter: time.Now().Add(time.Hour), IsCA: true, BasicConstraintsValid: true, KeyUsage: x509.KeyUsageCertSign | x509.KeyUsageDigitalSignature, ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth}, URIs: []*url.URL{identityURI}}
	der, err := x509.CreateCertificate(rand.Reader, template, parent, &key.PublicKey, parentKey)
	require.NoError(t, err)
	keyDER, err := x509.MarshalPKCS8PrivateKey(key)
	require.NoError(t, err)
	certificate, err := tls.X509KeyPair(pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der}), pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: keyDER}))
	require.NoError(t, err)
	return certificate
}

func issueTestCA(t *testing.T, name string) (*x509.Certificate, *ecdsa.PrivateKey, []byte) {
	t.Helper()
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	require.NoError(t, err)
	template := &x509.Certificate{SerialNumber: big.NewInt(time.Now().UnixNano()), Subject: pkix.Name{CommonName: name}, NotBefore: time.Now().Add(-time.Minute), NotAfter: time.Now().Add(time.Hour), IsCA: true, BasicConstraintsValid: true, KeyUsage: x509.KeyUsageCertSign | x509.KeyUsageDigitalSignature}
	der, err := x509.CreateCertificate(rand.Reader, template, template, &key.PublicKey, key)
	require.NoError(t, err)
	certificate, err := x509.ParseCertificate(der)
	require.NoError(t, err)
	return certificate, key, pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der})
}

func issueTestLeaf(t *testing.T, ca *x509.Certificate, caKey *ecdsa.PrivateKey, name string, dnsNames []string, uriNames []string, usages []x509.ExtKeyUsage) ([]byte, []byte, tls.Certificate) {
	return issueTestLeafAt(t, ca, caKey, name, dnsNames, uriNames, usages, time.Now().Add(-time.Minute), time.Now().Add(time.Hour))
}

func issueTestLeafAt(t *testing.T, ca *x509.Certificate, caKey *ecdsa.PrivateKey, name string, dnsNames []string, uriNames []string, usages []x509.ExtKeyUsage, notBefore, notAfter time.Time) ([]byte, []byte, tls.Certificate) {
	t.Helper()
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	require.NoError(t, err)
	var uris []*url.URL
	for _, rawURI := range uriNames {
		parsed, err := url.Parse(rawURI)
		require.NoError(t, err)
		uris = append(uris, parsed)
	}
	template := &x509.Certificate{SerialNumber: big.NewInt(time.Now().UnixNano()), Subject: pkix.Name{CommonName: name}, DNSNames: dnsNames, URIs: uris, NotBefore: notBefore, NotAfter: notAfter, KeyUsage: x509.KeyUsageDigitalSignature, ExtKeyUsage: usages}
	der, err := x509.CreateCertificate(rand.Reader, template, ca, &key.PublicKey, caKey)
	require.NoError(t, err)
	keyDER, err := x509.MarshalPKCS8PrivateKey(key)
	require.NoError(t, err)
	certPEM := pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der})
	keyPEM := pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: keyDER})
	certificate, err := tls.X509KeyPair(certPEM, keyPEM)
	require.NoError(t, err)
	return certPEM, keyPEM, certificate
}

func TestConventionalGRPCServerMTLSHandshake(t *testing.T) {
	material := writeTestMTLSMaterial(t)
	server, err := setupGRPCServer(t.Context(), &config.Config{
		GRPCTLSCertFile:       material.serverCertFile,
		GRPCTLSKeyFile:        material.serverKeyFile,
		GRPCClientCAFile:      material.caFile,
		GRPCAllowedClientURIs: material.allowedURIs,
	}, nil, nil, discardLogger())
	require.NoError(t, err)
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	require.NoError(t, err)
	go func() { _ = server.Serve(listener) }()
	t.Cleanup(func() { server.Stop(); _ = listener.Close() })

	caPEM, err := os.ReadFile(material.caFile)
	require.NoError(t, err)
	roots := x509.NewCertPool()
	require.True(t, roots.AppendCertsFromPEM(caPEM))
	check := func(t *testing.T, certificates []tls.Certificate, wantSuccess bool) {
		t.Helper()
		connection, err := grpc.NewClient(listener.Addr().String(), grpc.WithTransportCredentials(credentials.NewTLS(&tls.Config{MinVersion: tls.VersionTLS13, RootCAs: roots, Certificates: certificates, ServerName: material.serverName})))
		require.NoError(t, err)
		defer func() { require.NoError(t, connection.Close()) }()
		ctx, cancel := context.WithTimeout(t.Context(), 2*time.Second)
		defer cancel()
		_, err = grpc_health_v1.NewHealthClient(connection).Check(ctx, &grpc_health_v1.HealthCheckRequest{})
		if wantSuccess {
			require.NoError(t, err)
		} else {
			require.Error(t, err)
		}
	}

	t.Run("accepts trusted client", func(t *testing.T) { check(t, []tls.Certificate{material.clientCert}, true) })
	t.Run("accepts trusted probe identity", func(t *testing.T) { check(t, []tls.Certificate{material.probeCert}, true) })
	t.Run("rejects no client certificate", func(t *testing.T) { check(t, nil, false) })
	t.Run("rejects client from wrong CA", func(t *testing.T) { check(t, []tls.Certificate{material.wrongClientCert}, false) })
	t.Run("rejects same-CA client without URI identity", func(t *testing.T) { check(t, []tls.Certificate{material.noURICert}, false) })
	t.Run("rejects same-CA wrong URI identity", func(t *testing.T) { check(t, []tls.Certificate{material.wrongIdentityCert}, false) })
	t.Run("rejects same-CA client with multiple URI identities", func(t *testing.T) { check(t, []tls.Certificate{material.multiURICert}, false) })
	t.Run("rejects same-CA probe with dual EKU", func(t *testing.T) { check(t, []tls.Certificate{material.dualEKUCert}, false) })
	t.Run("rejects same-CA client CA certificate", func(t *testing.T) { check(t, []tls.Certificate{material.caClientCert}, false) })
}

func TestValidateConventionalServerCertificate(t *testing.T) {
	material := writeTestMTLSMaterial(t)
	now := time.Now()
	require.NoError(t, validateConventionalServerCertificate(material.serverCert, now))

	caCert, caKey, _ := issueTestCA(t, "validator-ca")
	issue := func(t *testing.T, usages []x509.ExtKeyUsage, notBefore, notAfter time.Time) tls.Certificate {
		t.Helper()
		_, _, certificate := issueTestLeafAt(t, caCert, caKey, "server", []string{material.serverName}, nil, usages, notBefore, notAfter)
		return certificate
	}
	for name, certificate := range map[string]tls.Certificate{
		"expired":        issue(t, []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth}, now.Add(-time.Hour), now.Add(-time.Second)),
		"not yet valid":  issue(t, []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth}, now.Add(time.Second), now.Add(time.Hour)),
		"missing EKU":    issue(t, nil, now.Add(-time.Minute), now.Add(time.Hour)),
		"dual EKU":       issue(t, []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth, x509.ExtKeyUsageClientAuth}, now.Add(-time.Minute), now.Add(time.Hour)),
		"any EKU":        issue(t, []x509.ExtKeyUsage{x509.ExtKeyUsageAny}, now.Add(-time.Minute), now.Add(time.Hour)),
		"CA certificate": {Certificate: [][]byte{caCert.Raw}},
	} {
		t.Run(name, func(t *testing.T) {
			require.Error(t, validateConventionalServerCertificate(certificate, now))
		})
	}

	t.Run("multiple leaf certificates", func(t *testing.T) {
		certificate := material.serverCert
		certificate.Certificate = append(certificate.Certificate, certificate.Certificate[0])
		require.Error(t, validateConventionalServerCertificate(certificate, now))
	})

	t.Run("malformed certificate", func(t *testing.T) {
		require.Error(t, validateConventionalServerCertificate(tls.Certificate{Certificate: [][]byte{[]byte("not-der")}}, now))
	})

	t.Run("leaf after CA", func(t *testing.T) {
		certificate := material.serverCert
		certificate.Certificate = append([][]byte{caCert.Raw}, certificate.Certificate...)
		require.Error(t, validateConventionalServerCertificate(certificate, now))
	})
}

func TestConventionalGRPCServerCredentialsRejectMissingFiles(t *testing.T) {
	_, err := setupGRPCServer(t.Context(), &config.Config{GRPCTLSCertFile: filepath.Join(t.TempDir(), "missing.crt"), GRPCTLSKeyFile: filepath.Join(t.TempDir(), "missing.key"), GRPCClientCAFile: filepath.Join(t.TempDir(), "missing-ca.crt")}, nil, nil, discardLogger())
	require.ErrorContains(t, err, "gRPC server certificate")
}

func TestConventionalGRPCServerCredentialsRejectInvalidClientCA(t *testing.T) {
	material := writeTestMTLSMaterial(t)

	_, err := conventionalGRPCServerCredentials(&config.Config{
		GRPCTLSCertFile:  material.serverCertFile,
		GRPCTLSKeyFile:   material.serverKeyFile,
		GRPCClientCAFile: filepath.Join(t.TempDir(), "missing-ca.crt"),
	})
	require.ErrorContains(t, err, "read gRPC client CA")

	invalidCA := filepath.Join(t.TempDir(), "ca.crt")
	require.NoError(t, os.WriteFile(invalidCA, []byte("not a certificate"), 0o600))
	_, err = conventionalGRPCServerCredentials(&config.Config{
		GRPCTLSCertFile:  material.serverCertFile,
		GRPCTLSKeyFile:   material.serverKeyFile,
		GRPCClientCAFile: invalidCA,
	})
	require.ErrorContains(t, err, "parse gRPC client CA")
}

func TestConventionalGRPCServerCredentialsRejectMissingClientIdentityAllowlist(t *testing.T) {
	material := writeTestMTLSMaterial(t)

	_, err := conventionalGRPCServerCredentials(&config.Config{
		GRPCTLSCertFile:  material.serverCertFile,
		GRPCTLSKeyFile:   material.serverKeyFile,
		GRPCClientCAFile: material.caFile,
	})

	require.ErrorContains(t, err, "FP_GRPC_ALLOWED_CLIENT_URIS")
}

func TestConventionalGRPCServerCredentialsRejectInvalidServerLeafContract(t *testing.T) {
	material := writeTestMTLSMaterial(t)
	directory := t.TempDir()
	certFile := filepath.Join(directory, "tls.crt")
	keyFile := filepath.Join(directory, "tls.key")
	require.NoError(t, os.WriteFile(certFile, pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: material.clientCert.Certificate[0]}), 0o600))
	clientKey, ok := material.clientCert.PrivateKey.(*ecdsa.PrivateKey)
	require.True(t, ok)
	keyDER, err := x509.MarshalPKCS8PrivateKey(clientKey)
	require.NoError(t, err)
	require.NoError(t, os.WriteFile(keyFile, pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: keyDER}), 0o600))

	_, err = conventionalGRPCServerCredentials(&config.Config{GRPCTLSCertFile: certFile, GRPCTLSKeyFile: keyFile, GRPCClientCAFile: material.caFile, GRPCAllowedClientURIs: material.allowedURIs})

	require.ErrorContains(t, err, "serverAuth-only")
}

func TestVerifyAllowedClientURIRejectsMissingVerifiedChain(t *testing.T) {
	err := verifyAllowedClientURI(map[string]struct{}{
		"spiffe://university.ecosystem/ns/university-ecosystem/sa/gateway": {},
	}, tls.ConnectionState{})

	require.EqualError(t, err, "verified client certificate chain is missing")
}

func TestVerifyAllowedClientURIRejectsInvalidLeafContracts(t *testing.T) {
	identity := "spiffe://university.ecosystem/ns/university-ecosystem/sa/gateway"
	identityURI, err := url.Parse(identity)
	require.NoError(t, err)
	now := time.Now()
	validLeaf := x509.Certificate{NotBefore: now.Add(-time.Minute), NotAfter: now.Add(time.Hour), ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth}, URIs: []*url.URL{identityURI}}
	allowed := map[string]struct{}{identity: {}}
	state := func(leaf x509.Certificate) tls.ConnectionState {
		return tls.ConnectionState{VerifiedChains: [][]*x509.Certificate{{&leaf}}}
	}
	require.NoError(t, verifyAllowedClientURI(allowed, state(validLeaf)))

	for name, mutate := range map[string]func(*x509.Certificate){
		"CA":            func(c *x509.Certificate) { c.IsCA = true },
		"expired":       func(c *x509.Certificate) { c.NotAfter = now.Add(-time.Second) },
		"not yet valid": func(c *x509.Certificate) { c.NotBefore = now.Add(time.Second) },
		"dual EKU": func(c *x509.Certificate) {
			c.ExtKeyUsage = []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth, x509.ExtKeyUsageServerAuth}
		},
		"missing URI":  func(c *x509.Certificate) { c.URIs = nil },
		"multiple URI": func(c *x509.Certificate) { c.URIs = []*url.URL{identityURI, identityURI} },
		"noncanonical URI": func(c *x509.Certificate) {
			alias, parseErr := url.Parse("spiffe://university.ecosystem/ns/university-ecosystem/sa/../sa/gateway")
			require.NoError(t, parseErr)
			c.URIs = []*url.URL{alias}
		},
	} {
		t.Run(name, func(t *testing.T) {
			leaf := validLeaf
			mutate(&leaf)
			require.Error(t, verifyAllowedClientURI(allowed, state(leaf)))
		})
	}
}
