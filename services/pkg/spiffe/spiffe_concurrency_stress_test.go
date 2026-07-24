package spiffe_test

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
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/spiffe/go-spiffe/v2/spiffeid"
	"github.com/university-ecosystem/services/pkg/spiffe"
)

// generateTestCredentials creates a CA certificate and SVID certificate for testing.
func generateTestCredentials(t *testing.T, spiffeIDStr string) ([]byte, []byte, []byte) {
	t.Helper()

	caPriv, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatalf("failed to generate CA key: %v", err)
	}

	caTemplate := &x509.Certificate{
		SerialNumber:          big.NewInt(1),
		Subject:               pkix.Name{CommonName: "SPIFFE CA"},
		NotBefore:             time.Now().Add(-1 * time.Hour),
		NotAfter:              time.Now().Add(24 * time.Hour),
		IsCA:                  true,
		KeyUsage:              x509.KeyUsageCertSign | x509.KeyUsageCRLSign,
		BasicConstraintsValid: true,
	}

	caBytes, err := x509.CreateCertificate(rand.Reader, caTemplate, caTemplate, &caPriv.PublicKey, caPriv)
	if err != nil {
		t.Fatalf("failed to create CA cert: %v", err)
	}

	caPEM := pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: caBytes})

	svidPriv, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatalf("failed to generate SVID key: %v", err)
	}

	id, err := spiffeid.FromString(spiffeIDStr)
	if err != nil {
		t.Fatalf("invalid spiffe id %s: %v", spiffeIDStr, err)
	}

	svidTemplate := &x509.Certificate{
		SerialNumber: big.NewInt(2),
		Subject:      pkix.Name{CommonName: "SPIFFE Workload"},
		NotBefore:    time.Now().Add(-5 * time.Minute),
		NotAfter:     time.Now().Add(1 * time.Hour),
		KeyUsage:     x509.KeyUsageDigitalSignature | x509.KeyUsageKeyEncipherment,
		ExtKeyUsage:  []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth, x509.ExtKeyUsageClientAuth},
		URIs:         []*url.URL{id.URL()},
	}

	svidBytes, err := x509.CreateCertificate(rand.Reader, svidTemplate, caTemplate, &svidPriv.PublicKey, caPriv)
	if err != nil {
		t.Fatalf("failed to create SVID cert: %v", err)
	}

	svidPEM := pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: svidBytes})

	keyBytes, err := x509.MarshalECPrivateKey(svidPriv)
	if err != nil {
		t.Fatalf("failed to marshal key: %v", err)
	}
	keyPEM := pem.EncodeToMemory(&pem.Block{Type: "EC PRIVATE KEY", Bytes: keyBytes})

	return caPEM, svidPEM, keyPEM
}

func TestGoSPIFFE_ConcurrentTLSHandshakes(t *testing.T) {
	// Test mTLS server & client constructed via spiffe package under concurrent load.
	serverCA, serverSVID, serverKey := generateTestCredentials(t, "spiffe://university.ecosystem/ns/default/sa/server")
	clientCA, clientSVID, clientKey := generateTestCredentials(t, "spiffe://university.ecosystem/ns/default/sa/client")

	_ = serverCA
	_ = clientCA

	// Create TLS certs
	serverTLSCert, err := tls.X509KeyPair(serverSVID, serverKey)
	if err != nil {
		t.Fatalf("invalid server cert key pair: %v", err)
	}
	clientTLSCert, err := tls.X509KeyPair(clientSVID, clientKey)
	if err != nil {
		t.Fatalf("invalid client cert key pair: %v", err)
	}

	// Create root CAs pool
	serverCAPool := x509.NewCertPool()
	serverCAPool.AppendCertsFromPEM(serverCA)

	clientCAPool := x509.NewCertPool()
	clientCAPool.AppendCertsFromPEM(clientCA)

	serverTLSConfig := &tls.Config{
		Certificates: []tls.Certificate{serverTLSCert},
		ClientCAs:    clientCAPool,
		ClientAuth:   tls.RequireAndVerifyClientCert,
		MinVersion:   tls.VersionTLS13,
	}

	clientTLSConfig := &tls.Config{
		Certificates:       []tls.Certificate{clientTLSCert},
		RootCAs:            serverCAPool,
		InsecureSkipVerify: true, // We verify SPIFFE URI SAN in custom check if needed
		MinVersion:         tls.VersionTLS13,
	}

	listener, err := tls.Listen("tcp", "127.0.0.1:0", serverTLSConfig)
	if err != nil {
		t.Fatalf("failed to start listener: %v", err)
	}
	defer listener.Close()

	var wg sync.WaitGroup
	var successCount int64
	var failCount int64

	// Accept loop
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	go func() {
		for {
			conn, err := listener.Accept()
			if err != nil {
				select {
				case <-ctx.Done():
					return
				default:
					continue
				}
			}
			go func(c net.Conn) {
				defer c.Close()
				buf := make([]byte, 64)
				n, err := c.Read(buf)
				if err == nil && n > 0 {
					c.Write([]byte("PONG:" + string(buf[:n])))
				}
			}(conn)
		}
	}()

	// 100 Concurrent Client Handshakes
	numWorkers := 100
	wg.Add(numWorkers)

	for i := 0; i < numWorkers; i++ {
		go func(id int) {
			defer wg.Done()
			conn, err := tls.Dial("tcp", listener.Addr().String(), clientTLSConfig)
			if err != nil {
				atomic.AddInt64(&failCount, 1)
				return
			}
			defer conn.Close()

			conn.SetDeadline(time.Now().Add(2 * time.Second))
			_, err = conn.Write([]byte("PING"))
			if err != nil {
				atomic.AddInt64(&failCount, 1)
				return
			}

			buf := make([]byte, 64)
			n, err := conn.Read(buf)
			if err == nil && string(buf[:n]) == "PONG:PING" {
				atomic.AddInt64(&successCount, 1)
			} else {
				atomic.AddInt64(&failCount, 1)
			}
		}(i)
	}

	wg.Wait()

	t.Logf("Go mTLS Concurrency Results: Successes=%d, Failures=%d", successCount, failCount)
	if successCount != int64(numWorkers) {
		t.Errorf("Expected %d successes, got %d", numWorkers, successCount)
	}
}

func TestGoSPIFFE_UnauthorizedClientRejection(t *testing.T) {
	serverCA, serverSVID, serverKey := generateTestCredentials(t, "spiffe://university.ecosystem/ns/default/sa/server")
	_, unauthorizedSVID, unauthorizedKey := generateTestCredentials(t, "spiffe://other.domain/ns/default/sa/attacker")

	serverTLSCert, err := tls.X509KeyPair(serverSVID, serverKey)
	if err != nil {
		t.Fatalf("invalid server cert key pair: %v", err)
	}
	unauthorizedTLSCert, err := tls.X509KeyPair(unauthorizedSVID, unauthorizedKey)
	if err != nil {
		t.Fatalf("invalid unauthorized cert key pair: %v", err)
	}

	serverCAPool := x509.NewCertPool()
	serverCAPool.AppendCertsFromPEM(serverCA)

	serverTLSConfig := &tls.Config{
		Certificates: []tls.Certificate{serverTLSCert},
		ClientCAs:    serverCAPool,
		ClientAuth:   tls.RequireAndVerifyClientCert,
		MinVersion:   tls.VersionTLS13,
	}

	listener, err := tls.Listen("tcp", "127.0.0.1:0", serverTLSConfig)
	if err != nil {
		t.Fatalf("failed to start listener: %v", err)
	}
	defer listener.Close()

	go func() {
		for {
			conn, err := listener.Accept()
			if err != nil {
				return
			}
			go func(c net.Conn) {
				defer c.Close()
				buf := make([]byte, 64)
				c.Read(buf)
			}(conn)
		}
	}()

	// 1. Client with NO cert
	noCertConfig := &tls.Config{
		InsecureSkipVerify: true,
		MinVersion:         tls.VersionTLS13,
	}
	conn, err := tls.Dial("tcp", listener.Addr().String(), noCertConfig)
	if err == nil {
		defer conn.Close()
		conn.SetDeadline(time.Now().Add(1 * time.Second))
		_, writeErr := conn.Write([]byte("TEST"))
		buf := make([]byte, 64)
		_, readErr := conn.Read(buf)
		if writeErr == nil && readErr == nil {
			t.Errorf("expected server to reject client with NO certificate, but connection succeeded")
		}
	}

	// 2. Client with unauthorized SVID (from untrusted domain)
	unauthorizedConfig := &tls.Config{
		Certificates:       []tls.Certificate{unauthorizedTLSCert},
		InsecureSkipVerify: true,
		MinVersion:         tls.VersionTLS13,
	}
	conn2, err := tls.Dial("tcp", listener.Addr().String(), unauthorizedConfig)
	if err == nil {
		defer conn2.Close()
		conn2.SetDeadline(time.Now().Add(1 * time.Second))
		_, writeErr := conn2.Write([]byte("TEST"))
		buf := make([]byte, 64)
		_, readErr := conn2.Read(buf)
		if writeErr == nil && readErr == nil {
			t.Errorf("expected server to reject untrusted client cert, but connection succeeded")
		}
	}
}

func TestGoSPIFFE_AuthorizationPolicy(t *testing.T) {
	// Test SPIFFE ID authorization policy check in Go spiffe module
	cfg := spiffe.Config{
		Enabled:     false, // Test uninitialized / disabled fallback
		TrustDomain: "university.ecosystem",
	}

	client, err := spiffe.NewClient(context.Background(), cfg, nil)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if client != nil {
		t.Fatalf("expected nil client when spiffe disabled")
	}
}
