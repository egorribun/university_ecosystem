// ssr-mtls-fixture is an isolated kind proof tool, never a production image binary.
package main

import (
	"context"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"sort"
	"strings"
	"syscall"
	"time"

	"github.com/spiffe/go-spiffe/v2/bundle/x509bundle"
	"github.com/spiffe/go-spiffe/v2/spiffeid"
	"github.com/spiffe/go-spiffe/v2/spiffetls/tlsconfig"
	"github.com/spiffe/go-spiffe/v2/svid/x509svid"
	"github.com/spiffe/go-spiffe/v2/workloadapi"
)

type fixtureConfig struct {
	mode   string
	socket string
	self   spiffeid.ID
	peer   spiffeid.ID
	target string
}

type fixtureReceipt struct {
	SelfID           string   `json:"selfID"`
	LeafSHA256       string   `json:"leafSHA256"`
	LeafNotAfterUnix int64    `json:"leafNotAfterUnix"`
	IssuerKeyID      string   `json:"issuerKeyID"`
	Roots            []string `json:"roots"`
}

func readFixtureConfig(args []string, getenv func(string) string) (fixtureConfig, error) {
	var cfg fixtureConfig
	if len(args) != 1 || (args[0] != "serve" && args[0] != "inspect" && args[0] != "check" && args[0] != "peer" && args[0] != "idle") {
		return cfg, errors.New("expected serve, inspect, check, peer or idle")
	}
	cfg.mode = args[0]
	cfg.socket = getenv("SPIFFE_ENDPOINT_SOCKET")
	socket, err := url.Parse(cfg.socket)
	if err != nil || socket.Scheme != "unix" || socket.Host != "" || socket.User != nil ||
		!strings.HasPrefix(socket.Path, "/") || socket.Path == "/" ||
		socket.RawQuery != "" || socket.ForceQuery || socket.Fragment != "" {
		return cfg, errors.New("invalid workload socket")
	}
	cfg.self, err = spiffeid.FromString(getenv("FIXTURE_SELF_ID"))
	if err != nil || cfg.self.Path() == "" {
		return cfg, errors.New("invalid fixture identity")
	}
	cfg.peer, err = spiffeid.FromString(getenv("FIXTURE_PEER_ID"))
	if err != nil || cfg.peer.Path() == "" || cfg.self == cfg.peer || cfg.self.TrustDomain() != cfg.peer.TrustDomain() {
		return cfg, errors.New("invalid peer identity")
	}
	if cfg.mode == "check" || cfg.mode == "peer" {
		cfg.target = getenv("FIXTURE_URL")
		target, parseErr := url.Parse(cfg.target)
		if parseErr != nil || target.Scheme != "https" || target.Hostname() == "" ||
			target.User != nil || target.Opaque != "" || target.RawQuery != "" ||
			target.ForceQuery || target.Fragment != "" || target.Path != "/health/ready" {
			return cfg, errors.New("invalid fixed health URL")
		}
	}
	return cfg, nil
}

type fixtureFetch func(context.Context) (*workloadapi.X509Context, error)

func fixtureSnapshot(ctx context.Context, cfg fixtureConfig, fetch fixtureFetch) (*x509svid.SVID, *x509bundle.Bundle, fixtureReceipt, error) {
	var receipt fixtureReceipt
	ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	current, err := fetch(ctx)
	if err != nil {
		return nil, nil, receipt, errors.New("workload fetch failed")
	}
	if current == nil || len(current.SVIDs) == 0 || current.SVIDs[0] == nil || current.Bundles == nil {
		return nil, nil, receipt, errors.New("missing workload identity")
	}
	svid := current.SVIDs[0]
	if svid.ID != cfg.self || len(svid.Certificates) == 0 || svid.PrivateKey == nil {
		return nil, nil, receipt, errors.New("unexpected workload identity")
	}
	bundle, err := current.Bundles.GetX509BundleForTrustDomain(cfg.self.TrustDomain())
	if err != nil || bundle == nil || bundle.Empty() {
		return nil, nil, receipt, errors.New("missing local trust bundle")
	}
	raw := make([][]byte, len(svid.Certificates))
	now := time.Now()
	for i, cert := range svid.Certificates {
		if cert == nil || now.Before(cert.NotBefore) || !now.Before(cert.NotAfter) {
			return nil, nil, receipt, errors.New("invalid identity validity")
		}
		raw[i] = cert.Raw
	}
	id, _, err := x509svid.ParseAndVerify(raw, bundle)
	if err != nil || id != cfg.self {
		return nil, nil, receipt, errors.New("untrusted workload identity")
	}
	for _, root := range bundle.X509Authorities() {
		if root == nil || now.Before(root.NotBefore) || !now.Before(root.NotAfter) || len(root.SubjectKeyId) == 0 {
			return nil, nil, receipt, errors.New("invalid local authority")
		}
		receipt.Roots = append(receipt.Roots, hex.EncodeToString(root.SubjectKeyId))
	}
	sort.Strings(receipt.Roots)
	leaf := svid.Certificates[0]
	digest := sha256.Sum256(leaf.Raw)
	receipt.SelfID = id.String()
	receipt.LeafSHA256 = hex.EncodeToString(digest[:])
	receipt.LeafNotAfterUnix = leaf.NotAfter.Unix()
	receipt.IssuerKeyID = hex.EncodeToString(leaf.AuthorityKeyId)
	return svid, bundle, receipt, nil
}

func fixtureHandler() http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			w.WriteHeader(http.StatusMethodNotAllowed)
			return
		}
		switch r.URL.Path {
		case "/health/ready":
			w.WriteHeader(http.StatusOK)
		case "/stream":
			ctx, cancel := context.WithTimeout(r.Context(), 120*time.Second)
			defer cancel()
			w.Header().Set("Content-Type", "text/plain")
			if _, err := io.WriteString(w, "OPEN\n"); err != nil {
				return
			}
			if err := http.NewResponseController(w).Flush(); err != nil {
				return
			}
			<-ctx.Done()
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	})
}

// fixtureBundleSource refreshes client trust on every incoming handshake while
// the server's own issued SVID remains intentionally frozen in memory.
type fixtureBundleSource struct {
	ctx   context.Context
	cfg   fixtureConfig
	fetch fixtureFetch
}

func (s fixtureBundleSource) GetX509BundleForTrustDomain(td spiffeid.TrustDomain) (*x509bundle.Bundle, error) {
	if td != s.cfg.self.TrustDomain() {
		return nil, errors.New("foreign client trust domain")
	}
	_, bundle, _, err := fixtureSnapshot(s.ctx, s.cfg, s.fetch)
	if err != nil {
		return nil, err
	}
	return bundle, nil
}

func peerReceipt(leaf *x509.Certificate, peer spiffeid.ID, bundle *x509bundle.Bundle) fixtureReceipt {
	digest := sha256.Sum256(leaf.Raw)
	receipt := fixtureReceipt{
		SelfID: peer.String(), LeafSHA256: hex.EncodeToString(digest[:]),
		LeafNotAfterUnix: leaf.NotAfter.Unix(), IssuerKeyID: hex.EncodeToString(leaf.AuthorityKeyId),
	}
	for _, root := range bundle.X509Authorities() {
		receipt.Roots = append(receipt.Roots, hex.EncodeToString(root.SubjectKeyId))
	}
	sort.Strings(receipt.Roots)
	return receipt
}

func serveFixture(ctx context.Context, listener net.Listener, svid *x509svid.SVID, bundle x509bundle.Source, peer spiffeid.ID) error {
	config := tlsconfig.MTLSServerConfig(svid, bundle, tlsconfig.AuthorizeID(peer))
	config.MinVersion = tls.VersionTLS13
	config.SessionTicketsDisabled = true
	server := &http.Server{
		Handler: fixtureHandler(), ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout: 5 * time.Second, WriteTimeout: 125 * time.Second,
		IdleTimeout: 5 * time.Second, MaxHeaderBytes: 32 << 10,
	}
	done := make(chan error, 1)
	go func() { done <- server.Serve(tls.NewListener(listener, config)) }()
	select {
	case err := <-done:
		return err
	case <-ctx.Done():
		closeErr := server.Close()
		serveErr := <-done
		if errors.Is(serveErr, http.ErrServerClosed) {
			serveErr = nil
		}
		return errors.Join(closeErr, serveErr)
	}
}

func checkFixture(ctx context.Context, cfg fixtureConfig, svid *x509svid.SVID, bundle *x509bundle.Bundle) error {
	_, err := inspectPeer(ctx, cfg, svid, bundle)
	return err
}

func inspectPeer(ctx context.Context, cfg fixtureConfig, svid *x509svid.SVID, bundle *x509bundle.Bundle) (fixtureReceipt, error) {
	tlsConfig := tlsconfig.MTLSClientConfig(svid, bundle, tlsconfig.AuthorizeID(cfg.peer))
	tlsConfig.MinVersion = tls.VersionTLS13
	tlsConfig.SessionTicketsDisabled = true
	transport := &http.Transport{
		Proxy: nil, TLSClientConfig: tlsConfig, DisableKeepAlives: true,
		TLSHandshakeTimeout: 5 * time.Second, ResponseHeaderTimeout: 5 * time.Second,
		TLSNextProto: make(map[string]func(string, *tls.Conn) http.RoundTripper),
	}
	defer transport.CloseIdleConnections()
	client := &http.Client{
		Transport: transport, Timeout: 5 * time.Second,
		CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse },
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, cfg.target, nil)
	if err != nil {
		return fixtureReceipt{}, err
	}
	response, err := client.Do(request)
	if err != nil {
		return fixtureReceipt{}, errors.New("authenticated health request failed")
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return fixtureReceipt{}, errors.New("health status is not 200")
	}
	if response.TLS == nil || len(response.TLS.PeerCertificates) == 0 {
		return fixtureReceipt{}, errors.New("missing authenticated peer")
	}
	return peerReceipt(response.TLS.PeerCertificates[0], cfg.peer, bundle), nil
}

func runFixture(ctx context.Context, cfg fixtureConfig, output io.Writer) (err error) {
	if cfg.mode == "idle" {
		<-ctx.Done()
		return nil
	}
	initCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	client, err := workloadapi.New(initCtx, workloadapi.WithAddr(cfg.socket))
	if err != nil {
		return errors.New("workload client initialization failed")
	}
	defer func() { err = errors.Join(err, client.Close()) }()
	svid, bundle, receipt, err := fixtureSnapshot(initCtx, cfg, client.FetchX509Context)
	if err != nil {
		return err
	}
	cancel()
	if cfg.mode == "peer" {
		peer, err := inspectPeer(ctx, cfg, svid, bundle)
		if err != nil {
			return err
		}
		return json.NewEncoder(output).Encode(peer)
	}
	if cfg.mode == "check" {
		if err := checkFixture(ctx, cfg, svid, bundle); err != nil {
			return err
		}
		_, err = fmt.Fprintln(output, "CHECK=200")
		return err
	}
	if cfg.mode == "inspect" {
		return json.NewEncoder(output).Encode(receipt)
	}
	listener, err := net.Listen("tcp", ":8000")
	if err != nil {
		return err
	}
	if err := json.NewEncoder(output).Encode(receipt); err != nil {
		return errors.Join(err, listener.Close())
	}
	// Deliberately retain this issued generation to test stale-peer rejection.
	return serveFixture(ctx, listener, svid, fixtureBundleSource{ctx: ctx, cfg: cfg, fetch: client.FetchX509Context}, cfg.peer)
}

func main() {
	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()
	cfg, err := readFixtureConfig(os.Args[1:], os.Getenv)
	if err == nil {
		err = runFixture(ctx, cfg, os.Stdout)
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, "fixture failed")
		os.Exit(1)
	}
}
