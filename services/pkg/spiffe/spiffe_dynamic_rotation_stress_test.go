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
	"github.com/spiffe/go-spiffe/v2/workloadapi"
)

// TestGoSPIFFE_DynamicSVIDRotationUnderConcurrency tests Go mTLS connection stability when SVID certificates are updated during active handshakes.
func TestGoSPIFFE_DynamicSVIDRotationUnderConcurrency(t *testing.T) {
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

	genSVID := func(spiffeIDStr string) ([]byte, []byte) {
		svidPriv, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
		if err != nil {
			t.Fatalf("failed to generate SVID key: %v", err)
		}

		id, err := spiffeid.FromString(spiffeIDStr)
		if err != nil {
			t.Fatalf("invalid spiffe id %s: %v", spiffeIDStr, err)
		}

		svidTemplate := &x509.Certificate{
			SerialNumber: big.NewInt(time.Now().UnixNano()),
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

		return svidPEM, keyPEM
	}

	serverSVID1, serverKey1 := genSVID("spiffe://university.ecosystem/ns/default/sa/server")
	clientSVID1, clientKey1 := genSVID("spiffe://university.ecosystem/ns/default/sa/client")

	// Create initial certificates
	serverTLSCert1, err := tls.X509KeyPair(serverSVID1, serverKey1)
	if err != nil {
		t.Fatalf("failed to parse server cert pair 1: %v", err)
	}
	clientTLSCert1, err := tls.X509KeyPair(clientSVID1, clientKey1)
	if err != nil {
		t.Fatalf("failed to parse client cert pair 1: %v", err)
	}

	serverCAPool := x509.NewCertPool()
	serverCAPool.AppendCertsFromPEM(caPEM)
	clientCAPool := x509.NewCertPool()
	clientCAPool.AppendCertsFromPEM(caPEM)

	// Thread-safe cert provider to simulate dynamic X509Source rotation
	var serverCert atomic.Pointer[tls.Certificate]
	serverCert.Store(&serverTLSCert1)

	var clientCert atomic.Pointer[tls.Certificate]
	clientCert.Store(&clientTLSCert1)

	serverTLSConfig := &tls.Config{
		GetCertificate: func(info *tls.ClientHelloInfo) (*tls.Certificate, error) {
			return serverCert.Load(), nil
		},
		ClientCAs:  clientCAPool,
		ClientAuth: tls.RequireAndVerifyClientCert,
		MinVersion: tls.VersionTLS13,
	}

	clientTLSConfig := &tls.Config{
		GetClientCertificate: func(info *tls.CertificateRequestInfo) (*tls.Certificate, error) {
			return clientCert.Load(), nil
		},
		RootCAs:            serverCAPool,
		InsecureSkipVerify: true,
		MinVersion:         tls.VersionTLS13,
	}

	listener, err := tls.Listen("tcp", "127.0.0.1:0", serverTLSConfig)
	if err != nil {
		t.Fatalf("failed to listen: %v", err)
	}
	defer listener.Close()

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Server accept loop
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
					c.Write([]byte("ACK:" + string(buf[:n])))
				}
			}(conn)
		}
	}()

	// Background goroutine rotating SVID certificates dynamically
	var rotationCount int64
	stopRotator := make(chan struct{})
	go func() {
		ticker := time.NewTicker(20 * time.Millisecond)
		defer ticker.Stop()

		for {
			select {
			case <-stopRotator:
				return
			case <-ticker.C:
				newServerSVID, newServerKey := genSVID("spiffe://university.ecosystem/ns/default/sa/server")
				newClientSVID, newClientKey := genSVID("spiffe://university.ecosystem/ns/default/sa/client")

				newServerCert, err1 := tls.X509KeyPair(newServerSVID, newServerKey)
				newClientCert, err2 := tls.X509KeyPair(newClientSVID, newClientKey)

				if err1 == nil && err2 == nil {
					serverCert.Store(&newServerCert)
					clientCert.Store(&newClientCert)
					atomic.AddInt64(&rotationCount, 1)
				}
			}
		}
	}()

	// Run 100 concurrent clients performing 5 requests each (total 500 handshakes)
	var wg sync.WaitGroup
	var successes int64
	var failures int64

	numClients := 100
	requestsPerClient := 5

	wg.Add(numClients)

	for i := 0; i < numClients; i++ {
		go func(clientID int) {
			defer wg.Done()
			for req := 0; req < requestsPerClient; req++ {
				conn, err := tls.Dial("tcp", listener.Addr().String(), clientTLSConfig)
				if err != nil {
					atomic.AddInt64(&failures, 1)
					continue
				}

				conn.SetDeadline(time.Now().Add(2 * time.Second))
				msg := "STRESS_PING"
				_, writeErr := conn.Write([]byte(msg))
				if writeErr != nil {
					conn.Close()
					atomic.AddInt64(&failures, 1)
					continue
				}

				buf := make([]byte, 64)
				n, readErr := conn.Read(buf)
				conn.Close()

				if readErr == nil && string(buf[:n]) == "ACK:"+msg {
					atomic.AddInt64(&successes, 1)
				} else {
					atomic.AddInt64(&failures, 1)
				}
			}
		}(i)
	}

	wg.Wait()
	close(stopRotator)

	t.Logf("Go SPIFFE Dynamic SVID Stress Results: Rotations=%d, Successes=%d, Failures=%d",
		atomic.LoadInt64(&rotationCount), successes, failures)

	expectedTotal := int64(numClients * requestsPerClient)
	if successes != expectedTotal {
		t.Errorf("Expected %d total successful handshakes, got %d (failures: %d)", expectedTotal, successes, failures)
	}
}

// Suppress unused error if workloadapi imported for types
var _ workloadapi.X509SourceOption
