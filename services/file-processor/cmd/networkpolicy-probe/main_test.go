package main

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	pb "github.com/university-ecosystem/core/gen/go/file_processor/v1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
	"math/big"
	"net"
	"os"
	"path/filepath"
	"time"

	"bytes"
	"encoding/json"
	"errors"
	"strings"
	"testing"
)

type failingReader struct{}

func (failingReader) Read([]byte) (int, error) { return 0, errors.New("fixture read error") }

type failingWriter struct{}

func (failingWriter) Write([]byte) (int, error) { return 0, errors.New("fixture write error") }

func TestRejectsInvalidAndOversizedInput(t *testing.T) {
	for name, input := range map[string]string{
		"empty": "", "missing-fields": "{}", "unknown-field": `{"unknown":"secret"}`,
		"trailing-object": "{} {}", "malformed": "{", "oversize-padding": "{}" + strings.Repeat(" ", 65535),
		"hidden-tail": "{}" + strings.Repeat(" ", 65535) + "garbage",
	} {
		t.Run(name, func(t *testing.T) {
			var output bytes.Buffer
			if err := run(strings.NewReader(input), &output); err != nil {
				t.Fatal(err)
			}
			var observed result
			if err := json.Unmarshal(output.Bytes(), &observed); err != nil {
				t.Fatal(err)
			}
			if observed.Result != "setup-error" || observed.Code != "" {
				t.Fatalf("unexpected safe result: %+v", observed)
			}
			if strings.Contains(output.String(), "secret") {
				t.Fatal("input leaked into output")
			}
		})
	}
}
func TestInputReadErrorIsSanitized(t *testing.T) {
	var output bytes.Buffer
	if err := run(failingReader{}, &output); err != nil {
		t.Fatal(err)
	}
	if output.String() != "{\"result\":\"setup-error\"}\n" {
		t.Fatal("unexpected result")
	}
}
func TestOutputErrorPropagates(t *testing.T) {
	if err := run(strings.NewReader("{}"), failingWriter{}); err == nil {
		t.Fatal("missing output error")
	}
}

// This is a hermetic client protocol test, not actual file-processor evidence.
type statusServer struct {
	pb.UnimplementedFileProcessingServiceServer
}

func (statusServer) ProcessFile(ctx context.Context, in *pb.ProcessFileRequest) (*pb.ProcessFileResponse, error) {
	md, _ := metadata.FromIncomingContext(ctx)
	if len(md.Get("authorization")) != 1 || md.Get("authorization")[0] != "Bearer fixture-token" {
		return nil, status.Error(codes.Unauthenticated, "missing test bearer")
	}
	return nil, status.Error(codes.InvalidArgument, "empty request")
}
func TestActualGeneratedClientWithMutualTLS(t *testing.T) {
	public, key, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	now := time.Now()
	template := &x509.Certificate{SerialNumber: big.NewInt(1), Subject: pkix.Name{CommonName: "fixture"}, DNSNames: []string{"fixture.test"}, NotBefore: now.Add(-time.Minute), NotAfter: now.Add(time.Hour), IsCA: true, BasicConstraintsValid: true, KeyUsage: x509.KeyUsageCertSign | x509.KeyUsageDigitalSignature, ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth, x509.ExtKeyUsageClientAuth}}
	der, err := x509.CreateCertificate(rand.Reader, template, template, public, key)
	if err != nil {
		t.Fatal(err)
	}
	encoded, err := x509.MarshalPKCS8PrivateKey(key)
	if err != nil {
		t.Fatal(err)
	}
	certificatePEM := pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der})
	keyPEM := pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: encoded})
	certificate, err := tls.X509KeyPair(certificatePEM, keyPEM)
	if err != nil {
		t.Fatal(err)
	}
	roots := x509.NewCertPool()
	if !roots.AppendCertsFromPEM(certificatePEM) {
		t.Fatal("invalid fixture roots")
	}
	directory := t.TempDir()
	certPath := filepath.Join(directory, "client.crt")
	keyPath := filepath.Join(directory, "client.key")
	if err := os.WriteFile(certPath, certificatePEM, 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(keyPath, keyPEM, 0600); err != nil {
		t.Fatal(err)
	}
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	server := grpc.NewServer(grpc.Creds(credentials.NewTLS(&tls.Config{MinVersion: tls.VersionTLS13, Certificates: []tls.Certificate{certificate}, ClientAuth: tls.RequireAndVerifyClientCert, ClientCAs: roots})))
	pb.RegisterFileProcessingServiceServer(server, statusServer{})
	stopped := make(chan error, 1)
	go func() { stopped <- server.Serve(listener) }()
	defer func() {
		server.Stop()
		if err := <-stopped; err != nil {
			t.Errorf("server stopped: %v", err)
		}
	}()
	input := request{Address: listener.Addr().String(), ServerName: "fixture.test", CAFile: certPath, CertificateFile: certPath, KeyFile: keyPath, Token: "fixture-token"}
	observed := probe(context.Background(), input)
	if observed.Result != "grpc-status" || observed.Code != "InvalidArgument" {
		t.Fatalf("unexpected result: %+v", observed)
	}
	input.Token = "other-fixture-token"
	observed = probe(context.Background(), input)
	if observed.Code != "Unauthenticated" {
		t.Fatalf("unexpected denial: %+v", observed)
	}
	input.ServerName = "wrong.test"
	observed = probe(context.Background(), input)
	if observed.Code != "Unavailable" && observed.Code != "DeadlineExceeded" {
		t.Fatalf("TLS mismatch did not fail transport: %+v", observed)
	}
}
