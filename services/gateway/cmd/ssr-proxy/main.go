// ssr-proxy bridges pod-local SSR HTTP to the backend's SPIFFE mTLS listener.
package main

import (
	"context"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"encoding/binary"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"os/signal"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/spiffe/go-spiffe/v2/bundle/x509bundle"
	"github.com/spiffe/go-spiffe/v2/spiffeid"
	"github.com/spiffe/go-spiffe/v2/spiffetls/tlsconfig"
	"github.com/spiffe/go-spiffe/v2/svid/x509svid"
	"github.com/spiffe/go-spiffe/v2/workloadapi"
)

const listenAddress = "127.0.0.1:18000"

var exitProcess = os.Exit

type proxyConfig struct {
	origin *url.URL
	socket string
	self   spiffeid.ID
	peer   spiffeid.ID
}

type checkedIdentity struct {
	source x509svid.Source
	id     spiffeid.ID
}

func (s checkedIdentity) GetX509SVID() (*x509svid.SVID, error) {
	svid, err := s.source.GetX509SVID()
	if err != nil {
		return nil, fmt.Errorf("SPIFFE identity unavailable: %w", err)
	}
	if svid == nil || svid.ID != s.id || len(svid.Certificates) == 0 || svid.Certificates[0] == nil {
		return nil, errors.New("unexpected SSR SPIFFE identity")
	}
	id, err := x509svid.IDFromCert(svid.Certificates[0])
	if err != nil || id != s.id {
		return nil, errors.New("unexpected SSR certificate identity")
	}
	if _, err := certificateDeadline(svid.Certificates); err != nil {
		return nil, err
	}
	return svid, nil
}

func readConfig(getenv func(string) string) (proxyConfig, error) {
	var cfg proxyConfig
	if getenv("SSR_MTLS_ENABLED") != "true" {
		return cfg, errors.New("SSR_MTLS_ENABLED must be true")
	}
	origin, err := parseOrigin(getenv("SSR_BACKEND_ORIGIN"))
	if err != nil {
		return cfg, err
	}
	cfg.origin = origin
	cfg.socket = getenv("SPIFFE_ENDPOINT_SOCKET")
	if !validSocket(cfg.socket) {
		return cfg, errors.New("SPIFFE_ENDPOINT_SOCKET must be an absolute Unix socket URL")
	}
	td, err := spiffeid.TrustDomainFromString(getenv("SSR_SPIFFE_TRUST_DOMAIN"))
	if err != nil {
		return cfg, errors.New("invalid SSR SPIFFE trust domain")
	}
	cfg.self, err = spiffeid.FromString(getenv("SSR_SPIFFE_ID"))
	if err != nil || cfg.self.TrustDomain() != td || cfg.self.Path() == "" {
		return cfg, errors.New("invalid SSR SPIFFE identity")
	}
	cfg.peer, err = spiffeid.FromString(getenv("SSR_BACKEND_SPIFFE_ID"))
	if err != nil || cfg.peer.TrustDomain() != td || cfg.peer.Path() == "" || cfg.peer == cfg.self {
		return cfg, errors.New("invalid backend SPIFFE identity")
	}
	return cfg, nil
}

func parseOrigin(value string) (*url.URL, error) {
	origin, err := url.Parse(value)
	if err != nil || origin.Scheme != "https" || origin.Hostname() == "" ||
		origin.User != nil || origin.RawQuery != "" || origin.ForceQuery || origin.Fragment != "" ||
		(origin.Path != "" && origin.Path != "/") || origin.Opaque != "" {
		return nil, errors.New("SSR_BACKEND_ORIGIN must be an HTTPS origin")
	}
	return origin, nil
}

func validSocket(value string) bool {
	socketURL, err := url.Parse(value)
	return err == nil && socketURL.Scheme == "unix" && socketURL.Host == "" && socketURL.User == nil &&
		strings.HasPrefix(socketURL.Path, "/") && socketURL.Path != "/" &&
		socketURL.RawQuery == "" && !socketURL.ForceQuery && socketURL.Fragment == ""
}

func certificateDeadline(certs []*x509.Certificate) (time.Time, error) {
	if len(certs) == 0 {
		return time.Time{}, errors.New("missing SPIFFE certificates")
	}
	var deadline time.Time
	now := time.Now()
	for _, cert := range certs {
		if cert == nil || now.Before(cert.NotBefore) || !now.Before(cert.NotAfter) {
			return time.Time{}, errors.New("SPIFFE material is not currently valid")
		}
		if deadline.IsZero() || cert.NotAfter.Before(deadline) {
			deadline = cert.NotAfter
		}
	}
	return deadline, nil
}

type fetchContext func(context.Context) (*workloadapi.X509Context, error)

type liveTransport struct {
	cfg   proxyConfig
	fetch fetchContext
}

func snapshot(ctx context.Context, cfg proxyConfig, fetch fetchContext) (*x509svid.SVID, *x509bundle.Bundle, time.Time, error) {
	fetchCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	current, err := fetch(fetchCtx)
	if err != nil {
		return nil, nil, time.Time{}, err
	}
	if current == nil || len(current.SVIDs) == 0 || current.Bundles == nil {
		return nil, nil, time.Time{}, errors.New("missing SPIFFE context")
	}
	svid, err := (checkedIdentity{source: current.SVIDs[0], id: cfg.self}).GetX509SVID()
	if err != nil {
		return nil, nil, time.Time{}, err
	}
	bundle, err := current.Bundles.GetX509BundleForTrustDomain(cfg.self.TrustDomain())
	if err != nil || bundle == nil || bundle.Empty() {
		return nil, nil, time.Time{}, errors.New("missing local SPIFFE bundle")
	}
	certs := append(append([]*x509.Certificate(nil), svid.Certificates...), bundle.X509Authorities()...)
	deadline, err := certificateDeadline(certs)
	if err != nil {
		return nil, nil, time.Time{}, err
	}
	raw := make([][]byte, len(svid.Certificates))
	for i, cert := range svid.Certificates {
		raw[i] = cert.Raw
	}
	if _, _, err := x509svid.ParseAndVerify(raw, bundle); err != nil {
		return nil, nil, time.Time{}, errors.New("SSR identity is not trusted by its local bundle")
	}
	return svid, bundle, deadline, nil
}

// generationFingerprint uses public certificate material only, never private keys.
func generationFingerprint(svid *x509svid.SVID, bundle *x509bundle.Bundle) [32]byte {
	var data []byte
	for _, group := range [][]*x509.Certificate{svid.Certificates, bundle.X509Authorities()} {
		data = binary.BigEndian.AppendUint64(data, uint64(len(group)))
		for _, cert := range group {
			data = binary.BigEndian.AppendUint64(data, uint64(len(cert.Raw)))
			data = append(data, cert.Raw...)
		}
	}
	return sha256.Sum256(data)
}

// watchGeneration bounds stale in-flight trust to one poll plus a bounded local
// Workload API refresh. Its stop function joins the worker before body teardown.
func watchGeneration(ctx context.Context, cfg proxyConfig, fetch fetchContext, fingerprint [32]byte) (context.Context, context.CancelFunc) {
	ctx, cancel := context.WithCancel(ctx)
	done := make(chan struct{})
	go func() {
		defer close(done)
		ticker := time.NewTicker(250 * time.Millisecond)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				refreshCtx, stop := context.WithTimeout(ctx, 250*time.Millisecond)
				svid, bundle, _, err := snapshot(refreshCtx, cfg, fetch)
				stop()
				if err != nil || generationFingerprint(svid, bundle) != fingerprint {
					cancel()
					return
				}
			}
		}
	}()
	return ctx, func() {
		cancel()
		<-done
	}
}

// peerDeadline installs expiry cancellation during the handshake, before any
// HTTP request body can be sent or response headers can be awaited.
func peerDeadline(ctx context.Context, cancel context.CancelFunc, deadline time.Time) (func(tls.ConnectionState) error, func()) {
	var mu sync.Mutex
	stopped := false
	timer := time.AfterFunc(time.Until(deadline), cancel)
	verify := func(state tls.ConnectionState) error {
		peerLimit, err := certificateDeadline(state.PeerCertificates)
		if err != nil {
			return err
		}
		mu.Lock()
		defer mu.Unlock()
		if stopped || ctx.Err() != nil {
			return context.Canceled
		}
		if peerLimit.Before(deadline) {
			deadline = peerLimit
			timer.Reset(time.Until(deadline))
		}
		return nil
	}
	stop := func() {
		mu.Lock()
		defer mu.Unlock()
		stopped = true
		timer.Stop()
	}
	return verify, stop
}

type cancelBody struct {
	io.ReadCloser
	cancel context.CancelFunc
}

func (b *cancelBody) Close() error {
	b.cancel()
	return b.ReadCloser.Close()
}

func (t liveTransport) RoundTrip(request *http.Request) (*http.Response, error) {
	svid, bundle, deadline, err := snapshot(request.Context(), t.cfg, t.fetch)
	if err != nil {
		return nil, err
	}
	deadlineCtx, cancelDeadline := context.WithDeadline(request.Context(), deadline)
	ctx, stopWatch := watchGeneration(deadlineCtx, t.cfg, t.fetch, generationFingerprint(svid, bundle))
	verifyPeerExpiry, stopExpiry := peerDeadline(ctx, cancelDeadline, deadline)
	cancel := func() {
		stopExpiry()
		cancelDeadline()
		stopWatch()
	}
	tlsConfig := tlsconfig.MTLSClientConfig(
		checkedIdentity{source: svid, id: t.cfg.self}, bundle, tlsconfig.AuthorizeID(t.cfg.peer),
	)
	tlsConfig.MinVersion = tls.VersionTLS13
	tlsConfig.SessionTicketsDisabled = true
	tlsConfig.VerifyConnection = verifyPeerExpiry
	transport := &http.Transport{
		Proxy:                 nil,
		DialContext:           (&net.Dialer{Timeout: 5 * time.Second}).DialContext,
		TLSClientConfig:       tlsConfig,
		TLSHandshakeTimeout:   5 * time.Second,
		ResponseHeaderTimeout: 15 * time.Second,
		DisableKeepAlives:     true,
		ForceAttemptHTTP2:     false,
		TLSNextProto:          make(map[string]func(string, *tls.Conn) http.RoundTripper),
	}
	// Each request obtains one coherent fresh generation; no pooled or resumed
	// connection can keep a removed trust root alive for a later dispatch.
	response, err := transport.RoundTrip(request.Clone(ctx))
	if err != nil {
		cancel()
		return nil, err
	}
	response.Body = &cancelBody{ReadCloser: response.Body, cancel: cancel}
	return response, nil
}

func newProxy(cfg proxyConfig, fetch fetchContext) http.Handler {
	proxy := &httputil.ReverseProxy{
		Transport: liveTransport{cfg: cfg, fetch: fetch},
		Rewrite: func(r *httputil.ProxyRequest) {
			r.SetURL(cfg.origin)
			r.Out.Host = cfg.origin.Host
			r.Out.URL.User = nil
			for key := range r.Out.Header {
				lower := strings.ToLower(key)
				if lower == "forwarded" || lower == "x-real-ip" ||
					strings.HasPrefix(lower, "x-forwarded-") || strings.HasPrefix(lower, "x-internal-") {
					r.Out.Header.Del(key)
				}
			}
		},
		ErrorHandler: func(w http.ResponseWriter, _ *http.Request, _ error) {
			http.Error(w, "backend transport unavailable", http.StatusBadGateway)
		},
	}
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodConnect || r.Method == http.MethodTrace || r.Header.Get("Upgrade") != "" {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		if r.URL.Path == "/_ssr_proxy/live" {
			w.WriteHeader(http.StatusOK)
			return
		}
		ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
		defer cancel()
		proxy.ServeHTTP(w, r.WithContext(ctx))
	})
}

func serve(ctx context.Context, listener net.Listener, handler http.Handler) error {
	server := &http.Server{
		Handler: handler, ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout: 30 * time.Second, WriteTimeout: 30 * time.Second,
		IdleTimeout: 30 * time.Second, MaxHeaderBytes: 32 << 10,
	}
	result := make(chan error, 1)
	go func() { result <- server.Serve(listener) }()
	select {
	case err := <-result:
		return err
	case <-ctx.Done():
		// Closing actively cancels outbound proxy requests and bounds shutdown.
		closeErr := server.Close()
		serveErr := <-result
		if errors.Is(serveErr, http.ErrServerClosed) {
			serveErr = nil
		}
		return errors.Join(closeErr, serveErr)
	}
}

func run(ctx context.Context, cfg proxyConfig) (err error) {
	initCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	client, err := workloadapi.New(initCtx, workloadapi.WithAddr(cfg.socket))
	if err != nil {
		return fmt.Errorf("initialize SSR SPIFFE client: %w", err)
	}
	defer func() { err = errors.Join(err, client.Close()) }()
	if _, _, _, err := snapshot(initCtx, cfg, client.FetchX509Context); err != nil {
		return err
	}
	cancel()
	listener, err := net.Listen("tcp4", listenAddress)
	if err != nil {
		return err
	}
	return serve(ctx, listener, newProxy(cfg, client.FetchX509Context))
}

func probe(ctx context.Context, endpoint string) (err error) {
	transport := &http.Transport{Proxy: nil}
	defer transport.CloseIdleConnections()
	client := &http.Client{
		Transport: transport, Timeout: 3 * time.Second,
		CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse },
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return err
	}
	response, err := client.Do(request)
	if err != nil {
		return err
	}
	defer func() { err = errors.Join(err, response.Body.Close()) }()
	if response.StatusCode != http.StatusOK {
		return fmt.Errorf("backend readiness returned HTTP %d", response.StatusCode)
	}
	return nil
}

func execute(ctx context.Context, args []string, getenv func(string) string) error {
	if len(args) == 1 {
		switch args[0] {
		case "probe":
			return probe(ctx, "http://"+listenAddress+"/health/ready")
		case "live":
			return probe(ctx, "http://"+listenAddress+"/_ssr_proxy/live")
		}
	}
	if len(args) != 0 {
		return errors.New("usage: ssr-proxy [probe|live]")
	}
	cfg, err := readConfig(getenv)
	if err != nil {
		return err
	}
	return run(ctx, cfg)
}

func main() {
	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()
	if err := execute(ctx, os.Args[1:], os.Getenv); err != nil {
		slog.Error("SSR proxy stopped", "error_type", fmt.Sprintf("%T", err))
		exitProcess(1)
	}
}
