package main

import (
	"bufio"
	"bytes"
	"context"
	"errors"
	"io"
	"log/slog"
	"net"
	"net/http"
	"net/http/httptest"
	"net/http/httptrace"
	"net/url"
	"os"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func testContainerID() string {
	return strings.Repeat("a", 64)
}

func TestRequestAllowlistAndNegativeControls(t *testing.T) {
	t.Parallel()
	var calls atomic.Int32
	transport := roundTripperFunc(func(*http.Request) (*http.Response, error) {
		calls.Add(1)
		return nil, errors.New("unexpected Docker request")
	})
	handler := newProxy(transport, time.Second, maxResponseBytes)
	tests := []struct {
		method   string
		target   string
		rawQuery string
		body     io.Reader
		status   int
	}{
		{http.MethodPost, "/_ping", "", nil, http.StatusMethodNotAllowed},
		{http.MethodHead, "/version", "", nil, http.StatusMethodNotAllowed},
		{http.MethodGet, "/events", "", nil, http.StatusNotFound},
		{http.MethodGet, "/v1.50/containers/abc/start", "", nil, http.StatusNotFound},
		{http.MethodGet, "/v1.50/containers/../json", "", nil, http.StatusNotFound},
		{http.MethodGet, "/v1.50/containers/%2e%2e/json", "", nil, http.StatusBadRequest},
		{http.MethodGet, "/v1.50/containers%2fjson", "", nil, http.StatusBadRequest},
		{http.MethodGet, "/v1.50/containers\\json", "", nil, http.StatusBadRequest},
		{http.MethodGet, "/v1.50/containers/json", "filters=%7B%7D", nil, http.StatusBadRequest},
		{http.MethodGet, "/v1.50/containers/json", "all=1&all=0", nil, http.StatusBadRequest},
		{http.MethodGet, "/v1.50/containers/json", "all=true", nil, http.StatusBadRequest},
		{http.MethodGet, "/v1.50/containers/json", "all=%zz", nil, http.StatusBadRequest},
		{http.MethodGet, "/v1.50/containers/" + testContainerID() + "/logs", "details=1", nil, http.StatusBadRequest},
		{http.MethodGet, "/v1.50/containers/" + testContainerID() + "/logs", "since=-1", nil, http.StatusBadRequest},
		{http.MethodGet, "/v1.50/networks", "", strings.NewReader("body"), http.StatusBadRequest},
		{http.MethodGet, "/healthz", "probe=1", nil, http.StatusBadRequest},
	}
	for _, test := range tests {
		request := httptest.NewRequest(test.method, test.target, test.body)
		request.URL.RawQuery = test.rawQuery
		response := httptest.NewRecorder()
		handler.ServeHTTP(response, request)
		if response.Code != test.status {
			t.Errorf("%s %s?%s status = %d, want %d", test.method, test.target, test.rawQuery, response.Code, test.status)
		}
	}
	chunked := httptest.NewRequest(http.MethodGet, "/v1.50/networks", strings.NewReader("body"))
	chunked.ContentLength = -1
	chunked.TransferEncoding = []string{"chunked"}
	chunkedResponse := httptest.NewRecorder()
	handler.ServeHTTP(chunkedResponse, chunked)
	if chunkedResponse.Code != http.StatusBadRequest {
		t.Fatalf("chunked request status = %d", chunkedResponse.Code)
	}
	health := httptest.NewRecorder()
	handler.ServeHTTP(health, httptest.NewRequest(http.MethodGet, "/healthz", nil))
	if health.Code != http.StatusOK || calls.Load() != 0 {
		t.Fatalf("local health status=%d upstream calls=%d", health.Code, calls.Load())
	}
}
func TestAllowedContainerListForwardsOnlyItsValidatedPathAndQuery(t *testing.T) {
	t.Parallel()
	var gotPath, gotQuery string
	server, closeProxy := testProxy(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath, gotQuery = r.URL.Path, r.URL.RawQuery
		w.Header().Set("Content-Type", "application/json")
		_, _ = io.WriteString(w, "[]")
	}), time.Second, maxResponseBytes)
	defer closeProxy()

	response, err := testHTTPClient(server).Get(server.URL + "/v1.50/containers/json?all=1")
	if err != nil {
		t.Fatal(err)
	}
	if response == nil {
		t.Fatal("HTTP GET returned a nil response")
		return
	}
	body, readErr := io.ReadAll(response.Body)
	_ = response.Body.Close()
	if readErr != nil || response.StatusCode != http.StatusOK || string(body) != "[]" {
		t.Fatalf("container list response = %d %q, %v", response.StatusCode, body, readErr)
	}
	if gotPath != "/v1.50/containers/json" || gotQuery != "all=1" {
		t.Fatalf("upstream request = %q?%s", gotPath, gotQuery)
	}
}
func TestQueryValidation(t *testing.T) {
	t.Parallel()
	valid := []struct {
		endpoint endpoint
		query    string
	}{
		{containers, ""}, {containers, "all=1"}, {networks, ""},
		{logs, "stdout=1&stderr=1&follow=1&timestamps=1&since=1720000000"},
		{logs, "tail="}, {logs, "tail=all"},
		{logs, "tail=25&since=1720000000.123456789"},
	}
	for _, test := range valid {
		if err := validateQuery(test.endpoint, test.query); err != nil {
			t.Errorf("valid query %q: %v", test.query, err)
		}
	}
	invalid := []struct {
		endpoint endpoint
		query    string
	}{
		{networks, "scope=local"}, {logs, "follow=yes"}, {logs, "since="},
		{logs, "since=123456789012345678901"}, {logs, "since=1&since=2"},
		{logs, "since=1720000000.1234567890"}, {logs, "since=1720000000.123x"},
		{logs, "tail=recent"}, {logs, "tail=-1"}, {logs, "tail=4294967296"}, {logs, "tail=12345678901"},
		{logs, "since=" + strings.Repeat("1", maxQueryBytes)}, {unknown, ""},
	}
	for _, test := range invalid {
		if err := validateQuery(test.endpoint, test.query); err == nil {
			t.Errorf("invalid query accepted: endpoint=%d query=%q", test.endpoint, test.query)
		}
	}
}

func TestDockerMetadataProjectionAndRedaction(t *testing.T) {
	t.Parallel()
	metadataMarker := "fixture-" + t.Name()
	fixture := func(raw string) []byte {
		raw = strings.ReplaceAll(raw, "CONTAINER_ID", testContainerID())
		raw = strings.ReplaceAll(raw, "METADATA_MARKER", metadataMarker)
		return []byte(raw)
	}
	list := fixture(`[{"Id":"CONTAINER_ID","Names":["/backend"],"Labels":{"com.docker.compose.project":"university","com.docker.compose.service":"backend","secret":"METADATA_MARKER"},"HostConfig":{"NetworkMode":"internal"},"NetworkSettings":{"Networks":{"internal":{"NetworkID":"net-1","IPAddress":"172.20.0.2","secret":"METADATA_MARKER"}}},"Ports":[{"PrivatePort":8000,"PublicPort":8000,"Type":"tcp"}],"Env":["PASSWORD=METADATA_MARKER"],"Mounts":[{"Source":"/private"}]}]`)
	projected, err := projectJSON(containers, list)
	if err != nil {
		t.Fatal(err)
	}
	for _, value := range []string{testContainerID(), "com.docker.compose.project", "university", "com.docker.compose.service", "backend", "NetworkMode", "NetworkID", "IPAddress", "PrivatePort"} {
		if !strings.Contains(string(projected), value) {
			t.Errorf("discovery field %q missing from %s", value, projected)
		}
	}
	for _, value := range []string{metadataMarker, "secret", "PASSWORD", "Mounts", "/private"} {
		if strings.Contains(string(projected), value) {
			t.Errorf("unneeded container data %q leaked in %s", value, projected)
		}
	}

	network, err := projectJSON(networks, fixture(`[{"Id":"net-1","Name":"internal","Scope":"local","Internal":true,"Ingress":false,"Labels":{"com.docker.compose.project":"university","secret":"METADATA_MARKER"},"Containers":{"secret":"METADATA_MARKER"}}]`))
	if err != nil || !strings.Contains(string(network), "Internal") || strings.Contains(string(network), metadataMarker) || strings.Contains(string(network), "secret") {
		t.Fatalf("network projection = %s, %v", network, err)
	}
	inspectResult, err := projectJSON(inspect, fixture(`{"Id":"CONTAINER_ID","Config":{"Tty":true,"Env":["PASSWORD=METADATA_MARKER"],"Labels":{"secret":"METADATA_MARKER"}},"State":{"Running":true,"FinishedAt":"0001-01-01T00:00:00Z","Pid":42},"Mounts":[{"Source":"/private"}],"HostConfig":{"Privileged":true}}`))
	if err != nil || !strings.Contains(string(inspectResult), `"Tty":true`) || !strings.Contains(string(inspectResult), `"Running":true`) || strings.Contains(string(inspectResult), metadataMarker) || strings.Contains(string(inspectResult), "PASSWORD") || strings.Contains(string(inspectResult), "Mounts") {
		t.Fatalf("inspect projection = %s, %v", inspectResult, err)
	}
	versionResult, err := projectJSON(version, []byte(`{"ApiVersion":"1.50","MinAPIVersion":"1.24","DockerRootDir":"/private"}`))
	if err != nil || !strings.Contains(string(versionResult), "MinAPIVersion") || strings.Contains(string(versionResult), "private") {
		t.Fatalf("version projection = %s, %v", versionResult, err)
	}
}

func TestStreamingIsUnmodifiedAndCancellationPropagates(t *testing.T) {
	t.Parallel()
	canceled := make(chan struct{})
	server, closeProxy := testProxy(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/vnd.docker.raw-stream")
		flusher := w.(http.Flusher)
		_, _ = io.WriteString(w, "log chunk\n")
		flusher.Flush()
		<-r.Context().Done()
		close(canceled)
	}), time.Second, maxResponseBytes)
	defer closeProxy()
	ctx, cancel := context.WithCancel(context.Background())
	request, _ := http.NewRequestWithContext(ctx, http.MethodGet, server.URL+"/v1.50/containers/"+testContainerID()+"/logs?stdout=1&follow=1&timestamps=1&since=0", nil)
	response, err := testHTTPClient(server).Do(request)
	if err != nil {
		t.Fatal(err)
	}
	if response == nil {
		t.Fatal("HTTP request returned a nil response")
		return
	}
	if response.Header.Get("Content-Type") != "application/vnd.docker.raw-stream" {
		t.Fatalf("stream content type = %q", response.Header.Get("Content-Type"))
	}
	line, err := bufio.NewReader(response.Body).ReadString('\n')
	if err != nil || line != "log chunk\n" {
		t.Fatalf("stream chunk = %q, %v", line, err)
	}
	cancel()
	_ = response.Body.Close()
	select {
	case <-canceled:
	case <-time.After(time.Second):
		t.Fatal("upstream log request stayed open after client cancellation")
	}
}

func TestStreamingTrailersAreDiscardedAfterEOF(t *testing.T) {
	t.Parallel()
	path := "/v1.50/containers/" + testContainerID() + "/logs?stdout=1"
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/vnd.docker.raw-stream")
		w.Header().Add("Trailer", "X-Docker-Private-Trailer")
		w.WriteHeader(http.StatusOK)
		_, _ = io.WriteString(w, "log chunk\n")
		w.(http.Flusher).Flush()
		w.Header().Set("X-Docker-Private-Trailer", "private-after-eof")
	}))
	defer upstream.Close()

	// Prove the upstream fixture really sends a trailer, so this is a negative
	// control for the complete ReverseProxy path rather than only map setup.
	directResponse, err := testHTTPClient(upstream).Get(upstream.URL + path)
	if err != nil {
		t.Fatal(err)
	}
	if directResponse == nil {
		t.Fatal("direct HTTP GET returned a nil response")
		return
	}
	if _, err := io.Copy(io.Discard, directResponse.Body); err != nil {
		t.Fatal(err)
	}
	_ = directResponse.Body.Close()
	if got := directResponse.Trailer.Get("X-Docker-Private-Trailer"); got != "private-after-eof" {
		t.Fatalf("upstream trailer fixture = %q", got)
	}

	upstreamURL, err := url.Parse(upstream.URL)
	if err != nil {
		t.Fatal(err)
	}
	dialer := &net.Dialer{Timeout: time.Second}
	transport := &http.Transport{DialContext: func(ctx context.Context, _, _ string) (net.Conn, error) {
		return dialer.DialContext(ctx, "tcp", upstreamURL.Host)
	}}
	proxy := httptest.NewServer(newProxy(transport, time.Second, maxResponseBytes))
	defer func() {
		proxy.Close()
		transport.CloseIdleConnections()
	}()
	response, err := testHTTPClient(proxy).Get(proxy.URL + path)
	if err != nil {
		t.Fatal(err)
	}
	if response == nil {
		t.Fatal("proxied HTTP GET returned a nil response")
		return
	}
	body, readErr := io.ReadAll(response.Body)
	_ = response.Body.Close()
	if readErr != nil || response.StatusCode != http.StatusOK || string(body) != "log chunk\n" {
		t.Fatalf("proxied log response = %d %q, %v", response.StatusCode, body, readErr)
	}
	if got := response.Header.Get("Trailer"); got != "" {
		t.Fatalf("Docker trailer declaration escaped: %q", got)
	}
	if got := response.Trailer.Get("X-Docker-Private-Trailer"); got != "" {
		t.Fatalf("Docker trailer escaped after EOF: %q", got)
	}
}

func TestDiscardTrailersClearsHeadersWithoutBody(t *testing.T) {
	trailers := http.Header{"X-Docker-Private-Trailer": {"private-without-body"}}
	response := &http.Response{
		Header:  http.Header{"Trailer": {"X-Docker-Private-Trailer"}},
		Trailer: trailers,
	}

	discardTrailers(response)

	if got := response.Header.Get("Trailer"); got != "" {
		t.Fatalf("trailer declaration survived without body: %q", got)
	}
	if response.Trailer != nil || len(trailers) != 0 {
		t.Fatalf("trailers survived without body: held=%v response=%v", trailers, response.Trailer)
	}
}

func TestDiscardTrailersClearsMapAssignedAtEOF(t *testing.T) {
	trailers := http.Header{"X-Docker-Private-Trailer": {"private-after-eof"}}
	response := &http.Response{Header: make(http.Header)}
	response.Body = &trailerAssignedAtEOFBody{response: response, trailers: trailers}
	discardTrailers(response)
	if _, ok := response.Body.(*trailerDiscardingBody); !ok {
		t.Fatal("body was not wrapped when the initial trailer map was nil")
	}
	if _, err := io.ReadAll(response.Body); err != nil {
		t.Fatalf("read streaming body: %v", err)
	}
	if len(trailers) != 0 || response.Trailer != nil {
		t.Fatalf("late trailers survived EOF: held=%v response=%v", trailers, response.Trailer)
	}
}

func TestDiscardTrailersClearsLiveMapOnClose(t *testing.T) {
	response := &http.Response{
		Header: make(http.Header),
		Body:   io.NopCloser(strings.NewReader("")),
	}
	discardTrailers(response)
	trailers := http.Header{"X-Docker-Private-Trailer": {"private-before-close"}}
	response.Trailer = trailers
	if err := response.Body.Close(); err != nil {
		t.Fatalf("close streaming body: %v", err)
	}
	if len(trailers) != 0 || response.Trailer != nil {
		t.Fatalf("trailers survived body close: held=%v response=%v", trailers, response.Trailer)
	}
}

func TestMetadataDeadlineAndResponseLimit(t *testing.T) {
	t.Parallel()
	t.Run("deadline", func(t *testing.T) {
		server, closeProxy := testProxy(t, http.HandlerFunc(func(_ http.ResponseWriter, r *http.Request) { <-r.Context().Done() }), 20*time.Millisecond, maxResponseBytes)
		defer closeProxy()
		response, err := testHTTPClient(server).Get(server.URL + "/v1.50/networks")
		if err != nil {
			t.Fatal(err)
		}
		if response == nil {
			t.Fatal("deadline HTTP GET returned a nil response")
			return
		}
		_ = response.Body.Close()
		if response.StatusCode != http.StatusBadGateway {
			t.Fatalf("deadline response = %d", response.StatusCode)
		}
	})
	t.Run("bounded metadata", func(t *testing.T) {
		server, closeProxy := testProxy(t, http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			_, _ = io.WriteString(w, `[{"Id":"`+testContainerID()+`"}]`)
		}), time.Second, 8)
		defer closeProxy()
		response, err := testHTTPClient(server).Get(server.URL + "/v1.50/containers/json")
		if err != nil {
			t.Fatal(err)
		}
		if response == nil {
			t.Fatal("metadata HTTP GET returned a nil response")
			return
		}
		_ = response.Body.Close()
		if response.StatusCode != http.StatusBadGateway {
			t.Fatalf("oversized response = %d", response.StatusCode)
		}
	})
}

func TestResponseHeadersErrorsAndInvalidPayloads(t *testing.T) {
	t.Parallel()
	cookieHeader := (&http.Cookie{
		Name:     "synthetic",
		Value:    t.Name(),
		Path:     "/",
		Secure:   true,
		HttpOnly: true,
		SameSite: http.SameSiteStrictMode,
	}).String()
	upstreamHandler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Api-Version", "1.50")
		w.Header().Set("Set-Cookie", cookieHeader)
		w.Header().Set("X-Internal-Path", "/var/lib/docker")
		if r.URL.Path == "/v1.50/networks" {
			w.WriteHeader(http.StatusNotFound)
			_, _ = io.WriteString(w, `{"message":"private daemon error"}`)
			return
		}
		_, _ = io.WriteString(w, "invalid json")
	})
	fixtureResponse := httptest.NewRecorder()
	upstreamHandler.ServeHTTP(fixtureResponse, httptest.NewRequest(http.MethodGet, "/_ping", nil))
	upstreamResponse := fixtureResponse.Result()
	if got := upstreamResponse.Header.Values("Set-Cookie"); len(got) != 1 || got[0] != cookieHeader {
		t.Fatalf("upstream cookie fixture = %v, want %q", got, cookieHeader)
	}
	_ = upstreamResponse.Body.Close()
	server, closeProxy := testProxy(t, upstreamHandler, time.Second, maxResponseBytes)
	defer closeProxy()
	response, err := testHTTPClient(server).Get(server.URL + "/_ping")
	if err != nil {
		t.Fatal(err)
	}
	if response == nil {
		t.Fatal("ping HTTP GET returned a nil response")
		return
	}
	if response.Header.Get("Api-Version") != "1.50" || len(response.Header.Values("Set-Cookie")) != 0 || response.Header.Get("X-Internal-Path") != "" {
		t.Fatalf("ping headers = %#v", response.Header)
	}
	_ = response.Body.Close()
	response, err = testHTTPClient(server).Get(server.URL + "/v1.50/networks")
	if err != nil {
		t.Fatal(err)
	}
	if response == nil {
		t.Fatal("network HTTP GET returned a nil response")
		return
	}
	body, readErr := io.ReadAll(response.Body)
	_ = response.Body.Close()
	if readErr != nil || response.StatusCode != http.StatusNotFound || strings.Contains(string(body), "private") {
		t.Fatalf("error response = %d %s, %v", response.StatusCode, body, readErr)
	}
	response, err = testHTTPClient(server).Get(server.URL + "/version")
	if err != nil {
		t.Fatal(err)
	}
	if response == nil {
		t.Fatal("version HTTP GET returned a nil response")
		return
	}
	_ = response.Body.Close()
	if response.StatusCode != http.StatusBadGateway {
		t.Fatalf("invalid JSON response = %d", response.StatusCode)
	}
}

func TestRunServeAndMainLifecycle(t *testing.T) {
	originalSignal, originalListen, originalMain, originalExit := signalContext, listenTCP, runProcess, exitProcess
	t.Cleanup(func() {
		signalContext, listenTCP, runProcess, exitProcess = originalSignal, originalListen, originalMain, originalExit
	})
	signalCtx, stopSignal := originalSignal()
	stopSignal()
	select {
	case <-signalCtx.Done():
	case <-time.After(time.Second):
		t.Fatal("signal context cancel did not stop the context")
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	signalContext = func() (context.Context, context.CancelFunc) { return ctx, func() {} }
	listenTCP = func(_, _ string) (net.Listener, error) { return nil, errors.New("listen denied") }
	if err := run(); err == nil || !strings.Contains(err.Error(), "listen for Docker log proxy") {
		t.Fatalf("run listen error = %v", err)
	}
	listenTCP = func(_, _ string) (net.Listener, error) { return net.Listen("tcp", "127.0.0.1:0") }
	if err := run(); err != nil {
		t.Fatalf("run canceled = %v", err)
	}
	closed, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	_ = closed.Close()
	if err := serve(context.Background(), closed, http.NotFoundHandler()); err == nil {
		t.Fatal("closed listener returned no error")
	}
	if _, err := dialDockerSocket(cancelledContext(t), "tcp", "ignored"); err == nil {
		t.Fatal("canceled Docker socket dial succeeded")
	}
	var output bytes.Buffer
	oldLogger := slog.Default()
	slog.SetDefault(slog.New(slog.NewTextHandler(&output, nil)))
	t.Cleanup(func() { slog.SetDefault(oldLogger) })
	exitCalls := 0
	exitCode := 0
	exitProcess = func(code int) {
		exitCalls++
		exitCode = code
	}
	runProcess = func() error { return errors.New("startup failed") }
	main()
	if !strings.Contains(output.String(), "startup failed") || exitCalls != 1 || exitCode != 1 {
		t.Fatalf("main error log=%q exit calls=%d code=%d", output.String(), exitCalls, exitCode)
	}
	runProcess = func() error { return nil }
	main()
	if exitCalls != 1 {
		t.Fatalf("successful main called exit %d times", exitCalls-1)
	}
}

func TestMainHealthcheckExitContract(t *testing.T) {
	originalArgs := os.Args
	originalURL := healthcheckURL
	originalRun, originalExit := runProcess, exitProcess
	t.Cleanup(func() {
		os.Args = originalArgs
		healthcheckURL = originalURL
		runProcess, exitProcess = originalRun, originalExit
	})

	var status atomic.Int32
	status.Store(http.StatusOK)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(int(status.Load()))
	}))
	defer server.Close()
	healthcheckURL = server.URL + "/healthz"
	os.Args = []string{"docker-log-proxy", "--healthcheck"}

	var output bytes.Buffer
	oldLogger := slog.Default()
	slog.SetDefault(slog.New(slog.NewTextHandler(&output, nil)))
	t.Cleanup(func() { slog.SetDefault(oldLogger) })

	runCalls := 0
	exitCodes := make([]int, 0, 1)
	runProcess = func() error {
		runCalls++
		return nil
	}
	exitProcess = func(code int) { exitCodes = append(exitCodes, code) }

	main()
	if runCalls != 0 || len(exitCodes) != 0 {
		t.Fatalf("successful healthcheck ran service %d times and exited with %v", runCalls, exitCodes)
	}

	status.Store(http.StatusServiceUnavailable)
	main()
	if runCalls != 0 || len(exitCodes) != 1 || exitCodes[0] != 1 {
		t.Fatalf("failed healthcheck ran service %d times and exited with %v", runCalls, exitCodes)
	}
	if !strings.Contains(output.String(), "health check failed") {
		t.Fatalf("failed healthcheck was not logged: %q", output.String())
	}
}

func TestCheckHealthEndpointRejectsResponseWithoutBody(t *testing.T) {
	var response *http.Response
	client := &http.Client{
		Transport: roundTripperFunc(func(request *http.Request) (*http.Response, error) {
			response = &http.Response{
				StatusCode: http.StatusTemporaryRedirect,
				Header:     http.Header{"Location": []string{"/healthz"}},
				Body:       io.NopCloser(strings.NewReader("")),
				Request:    request,
			}
			return response, nil
		}),
		CheckRedirect: func(*http.Request, []*http.Request) error {
			if response == nil {
				return errors.New("redirect response unavailable")
			}
			response.Body = nil
			return http.ErrUseLastResponse
		},
	}

	err := checkHealthEndpoint(client, "http://docker-engine/redirect")
	if err == nil || err.Error() != "docker log proxy health response unavailable" {
		t.Fatalf("missing response body error = %v", err)
	}
}

func TestCheckHealthEndpointStatusAndRedirects(t *testing.T) {
	t.Run("healthy response", func(t *testing.T) {
		var calls atomic.Int32
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			calls.Add(1)
			if r.Method != http.MethodGet || r.URL.Path != "/healthz" {
				t.Errorf("health request = %s %q", r.Method, r.URL.Path)
			}
			w.WriteHeader(http.StatusOK)
		}))
		defer server.Close()

		if err := checkHealthEndpoint(newHealthcheckClient(time.Second), server.URL+"/healthz"); err != nil {
			t.Fatalf("check healthy endpoint: %v", err)
		}
		if calls.Load() != 1 {
			t.Fatalf("healthy endpoint received %d requests, want one", calls.Load())
		}
	})

	t.Run("non-200 response", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			w.WriteHeader(http.StatusServiceUnavailable)
		}))
		defer server.Close()

		err := checkHealthEndpoint(newHealthcheckClient(time.Second), server.URL+"/healthz")
		if err == nil || !strings.Contains(err.Error(), "503 Service Unavailable") {
			t.Fatalf("non-200 healthcheck error = %v", err)
		}
	})

	t.Run("does not follow redirects", func(t *testing.T) {
		var destinationCalls atomic.Int32
		destination := httptest.NewServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
			destinationCalls.Add(1)
		}))
		defer destination.Close()
		redirect := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			w.Header().Set("Location", destination.URL)
			w.WriteHeader(http.StatusTemporaryRedirect)
		}))
		defer redirect.Close()

		err := checkHealthEndpoint(newHealthcheckClient(time.Second), redirect.URL)
		if err == nil || !strings.Contains(err.Error(), "307 Temporary Redirect") {
			t.Fatalf("redirect healthcheck error = %v", err)
		}
		if destinationCalls.Load() != 0 {
			t.Fatalf("healthcheck followed redirect %d times", destinationCalls.Load())
		}
	})
}

func TestCheckHealthEndpointBoundsRequests(t *testing.T) {
	t.Run("bounded request", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(_ http.ResponseWriter, r *http.Request) {
			<-r.Context().Done()
		}))
		defer server.Close()

		client := newHealthcheckClient(30 * time.Millisecond)
		if client.Timeout != 30*time.Millisecond {
			t.Fatalf("healthcheck client timeout = %s", client.Timeout)
		}
		if err := checkHealthEndpoint(client, server.URL); err == nil {
			t.Fatal("healthcheck succeeded despite the server not responding")
		}
	})

	t.Run("connection refused", func(t *testing.T) {
		server := httptest.NewServer(http.NotFoundHandler())
		endpoint := server.URL
		server.Close()

		if err := checkHealthEndpoint(newHealthcheckClient(time.Second), endpoint); err == nil {
			t.Fatal("healthcheck succeeded without a listener")
		}
	})

	t.Run("invalid URL", func(t *testing.T) {
		if err := checkHealthEndpoint(newHealthcheckClient(time.Second), "http://[::1"); err == nil {
			t.Fatal("invalid healthcheck URL was accepted")
		}
	})
}

func TestCheckHealthEndpointReportsBodyCloseFailure(t *testing.T) {
	t.Run("response close error", func(t *testing.T) {
		closeErr := errors.New("health response close failed")
		body := &closeTrackingBody{reader: strings.NewReader(""), closeErr: closeErr}
		client := &http.Client{Transport: roundTripperFunc(func(request *http.Request) (*http.Response, error) {
			return &http.Response{
				StatusCode: http.StatusOK,
				Status:     "200 OK",
				Header:     make(http.Header),
				Body:       body,
				Request:    request,
			}, nil
		})}

		if err := checkHealthEndpoint(client, "http://127.0.0.1/healthz"); !errors.Is(err, closeErr) {
			t.Fatalf("response close error = %v, want wrapped close failure", err)
		}
		if body.closes != 1 {
			t.Fatalf("health response body closed %d times, want once", body.closes)
		}
	})
}

func TestGracefulShutdownContextPreservesValuesAndAddsIndependentDeadline(t *testing.T) {
	type contextKey struct{}
	parent, cancel := context.WithCancel(context.WithValue(context.Background(), contextKey{}, "trace-value"))
	cancel()

	shutdown, stop := gracefulShutdownContext(parent, time.Minute)
	defer stop()
	if got := shutdown.Value(contextKey{}); got != "trace-value" {
		t.Fatalf("shutdown context value = %v", got)
	}
	if err := shutdown.Err(); err != nil {
		t.Fatalf("shutdown context inherited cancellation: %v", err)
	}
	deadline, ok := shutdown.Deadline()
	if !ok || time.Until(deadline) <= 0 || time.Until(deadline) > time.Minute {
		t.Fatalf("shutdown deadline = %v, present=%v", deadline, ok)
	}
}

func TestServeClosesListenerWhenGracefulShutdownTimesOut(t *testing.T) {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	releaseHandler := make(chan struct{})
	started := make(chan struct{})
	serveResult := make(chan error, 1)
	handler := http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
		writer.WriteHeader(http.StatusOK)
		writer.(http.Flusher).Flush()
		close(started)
		<-releaseHandler
	})
	go func() {
		serveResult <- serveWithShutdownTimeout(ctx, listener, handler, 20*time.Millisecond)
	}()
	t.Cleanup(func() {
		cancel()
		close(releaseHandler)
		_ = listener.Close()
	})

	response, err := http.Get("http://" + listener.Addr().String())
	if err != nil {
		t.Fatal(err)
	}
	if response == nil {
		t.Fatal("shutdown HTTP GET returned a nil response")
		return
	}
	defer func() { _ = response.Body.Close() }()
	select {
	case <-started:
	case <-time.After(time.Second):
		t.Fatal("handler did not start before shutdown")
	}
	cancel()
	select {
	case err := <-serveResult:
		if !errors.Is(err, context.DeadlineExceeded) {
			t.Fatalf("serve after forced close = %v, want shutdown deadline", err)
		}
	case <-time.After(time.Second):
		t.Fatal("serve did not exit after forced listener close")
	}
}

func TestServeShutdownErrorCombinations(t *testing.T) {
	shutdownErr := errors.New("shutdown timed out")
	closeErr := errors.New("server close failed")
	serveErr := errors.New("listener serve failed")

	closed := joinShutdownErrors(shutdownErr, closeErr, http.ErrServerClosed)
	if !errors.Is(closed, shutdownErr) || !errors.Is(closed, closeErr) || errors.Is(closed, http.ErrServerClosed) {
		t.Fatalf("closed-server shutdown errors = %v", closed)
	}
	unexpected := joinShutdownErrors(shutdownErr, closeErr, serveErr)
	if !errors.Is(unexpected, shutdownErr) || !errors.Is(unexpected, closeErr) || !errors.Is(unexpected, serveErr) {
		t.Fatalf("unexpected serve shutdown errors = %v", unexpected)
	}
	if got := unexpectedServeErrorAfterShutdown(http.ErrServerClosed); got != nil {
		t.Fatalf("expected normal server close to be suppressed, got %v", got)
	}
	if got := unexpectedServeErrorAfterShutdown(serveErr); got != serveErr {
		t.Fatalf("unexpected serve error = %v, want %v", got, serveErr)
	}
}

func TestPathClassifier(t *testing.T) {
	t.Parallel()
	valid := map[string]endpoint{
		"/healthz": health, "/_ping": ping, "/version": version,
		"/v1.50/containers/json": containers, "/v1.50/networks": networks,
		"/v1.50/containers/" + testContainerID() + "/json": inspect,
		"/v1.50/containers/" + testContainerID() + "/logs": logs,
	}
	for path, expected := range valid {
		got, err := classifyPath(&url.URL{Path: path})
		if err != nil || got != expected {
			t.Errorf("classify %s = %d, %v; want %d", path, got, err, expected)
		}
	}
	for _, path := range []string{
		"/v1/network", "/v1.a/networks", "/v1.50/events", "/v1.50/containers/abc/json",
		"/v1.50/containers/" + testContainerID() + "/start",
	} {
		if got, err := classifyPath(&url.URL{Path: path}); err != nil || got != unknown {
			t.Errorf("invalid route %s = %d, %v", path, got, err)
		}
	}
}

func TestDefensiveQueryAndResponsePathValidation(t *testing.T) {
	if err := validateQuery(endpoint(255), ""); err == nil {
		t.Fatal("unknown endpoint passed query validation")
	}
	if validSinceTimestamp("9223372036854775808") {
		t.Fatal("overflowing log timestamp was accepted")
	}
	response := &http.Response{
		Header:  make(http.Header),
		Request: &http.Request{URL: &url.URL{Path: "/v1.50/containers\\json"}},
	}
	if err := sanitizeResponse(response, maxResponseBytes); err == nil {
		t.Fatal("ambiguous response request path was accepted")
	}
}

func TestSetBodyClearsTransportFraming(t *testing.T) {
	response := &http.Response{
		Header:           make(http.Header),
		Body:             io.NopCloser(strings.NewReader("old")),
		TransferEncoding: []string{"chunked"},
		Trailer:          http.Header{"X-Private": {"value"}},
	}
	if err := setBody(response, []byte("safe"), "application/json"); err != nil {
		t.Fatal(err)
	}
	if len(response.TransferEncoding) != 0 || response.Trailer != nil {
		t.Fatalf("transport framing survived body replacement: transfer=%v trailer=%v", response.TransferEncoding, response.Trailer)
	}
	body, err := io.ReadAll(response.Body)
	if err != nil || string(body) != "safe" || response.Header.Get("Content-Length") != "4" {
		t.Fatalf("replacement body=%q content-length=%q err=%v", body, response.Header.Get("Content-Length"), err)
	}
	_ = response.Body.Close()
}
func TestReadBodyAndUnsupportedProjection(t *testing.T) {
	t.Parallel()
	for _, test := range []struct {
		body  io.ReadCloser
		limit int64
	}{
		{nil, 3},
		{io.NopCloser(strings.NewReader("")), -1},
		{io.NopCloser(strings.NewReader("123")), 2},
		{readFailure{}, 3},
	} {
		if _, err := readBody(test.body, test.limit); err == nil {
			t.Error("expected bounded body error")
		}
	}
	for _, route := range []endpoint{unknown, health, ping, logs, endpoint(255)} {
		if _, err := projectJSON(route, []byte("{}")); err == nil {
			t.Errorf("unsupported JSON endpoint %d was accepted", route)
		}
	}
	for _, route := range []endpoint{version, containers, networks, inspect} {
		if _, err := projectJSON(route, []byte("{")); err == nil {
			t.Errorf("invalid JSON accepted for endpoint %d", route)
		}
	}
}

func TestReadBodyAndSetBodyReportCloseFailuresOnce(t *testing.T) {
	closeErr := errors.New("close failed")

	trackedReadBody := &closeTrackingBody{reader: strings.NewReader("metadata"), closeErr: closeErr}
	if _, err := readBody(trackedReadBody, 32); !errors.Is(err, closeErr) {
		t.Fatalf("readBody error = %v, want close failure", err)
	}
	if trackedReadBody.closes != 1 {
		t.Fatalf("readBody closed the source %d times, want once", trackedReadBody.closes)
	}

	replacementBody := &closeTrackingBody{reader: strings.NewReader("old"), closeErr: closeErr}
	response := &http.Response{Header: make(http.Header), Body: replacementBody}
	if err := setBody(response, []byte("safe"), "application/json"); !errors.Is(err, closeErr) {
		t.Fatalf("setBody error = %v, want close failure", err)
	}
	if replacementBody.closes != 1 {
		t.Fatalf("setBody closed the source %d times, want once", replacementBody.closes)
	}
	if response.Body != http.NoBody {
		t.Fatalf("failed body replacement retained an already-closed response body: %T", response.Body)
	}
}

func TestSanitizeResponseClosesMetadataBodyOnce(t *testing.T) {
	originalBody := &closeTrackingBody{reader: strings.NewReader("{\"ApiVersion\":\"1.50\"}")}
	response := &http.Response{
		StatusCode: http.StatusOK,
		Header:     make(http.Header),
		Request:    &http.Request{URL: &url.URL{Path: "/version"}},
		Body:       originalBody,
	}
	if err := sanitizeResponse(response, maxResponseBytes); err != nil {
		t.Fatalf("sanitize metadata response: %v", err)
	}
	if originalBody.closes != 1 {
		t.Fatalf("metadata source closed %d times, want once", originalBody.closes)
	}
	if response.Body == originalBody {
		t.Fatal("sanitized response retained the already-closed source body")
	}
	body, err := io.ReadAll(response.Body)
	if err != nil || string(body) != "{\"ApiVersion\":\"1.50\",\"MinAPIVersion\":\"\"}" {
		t.Fatalf("projected response body=%q err=%v", body, err)
	}
	if err := response.Body.Close(); err != nil {
		t.Fatalf("close projected response: %v", err)
	}
}

func TestSetBodySupportsAbsentResponseBody(t *testing.T) {
	response := &http.Response{Header: make(http.Header)}
	if err := setBody(response, []byte("safe"), "application/json"); err != nil {
		t.Fatalf("replace absent body: %v", err)
	}
	body, err := io.ReadAll(response.Body)
	if err != nil || string(body) != "safe" {
		t.Fatalf("replacement body=%q err=%v", body, err)
	}
	if err := response.Body.Close(); err != nil {
		t.Fatalf("close replacement body: %v", err)
	}
}

func testProxy(t *testing.T, upstream http.Handler, timeout time.Duration, limit int64) (*httptest.Server, func()) {
	t.Helper()
	upstreamServer := httptest.NewServer(upstream)
	upstreamURL, err := url.Parse(upstreamServer.URL)
	if err != nil {
		t.Fatal(err)
	}
	dialer := &net.Dialer{Timeout: time.Second}
	transport := &http.Transport{
		DialContext: func(ctx context.Context, _, _ string) (net.Conn, error) {
			return dialer.DialContext(ctx, "tcp", upstreamURL.Host)
		},
		ResponseHeaderTimeout: time.Second,
	}
	proxyServer := httptest.NewServer(newProxy(transport, timeout, limit))
	return proxyServer, func() {
		proxyServer.Close()
		transport.CloseIdleConnections()
		upstreamServer.Close()
	}
}

func cancelledContext(t *testing.T) context.Context {
	t.Helper()
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	return ctx
}

type roundTripperFunc func(*http.Request) (*http.Response, error)

func (fn roundTripperFunc) RoundTrip(request *http.Request) (*http.Response, error) {
	return fn(request)
}

type readFailure struct{}

func (readFailure) Read([]byte) (int, error) { return 0, errors.New("read failed") }
func (readFailure) Close() error             { return nil }

type closeTrackingBody struct {
	reader   io.Reader
	closeErr error
	closes   int
}

func (body *closeTrackingBody) Read(buffer []byte) (int, error) {
	return body.reader.Read(buffer)
}

func (body *closeTrackingBody) Close() error {
	body.closes++
	return body.closeErr
}

type trailerAssignedAtEOFBody struct {
	response *http.Response
	trailers http.Header
}

func (body *trailerAssignedAtEOFBody) Read([]byte) (int, error) {
	body.response.Trailer = body.trailers
	return 0, io.EOF
}

func (body *trailerAssignedAtEOFBody) Close() error { return nil }

func testHTTPClient(_ *httptest.Server) *http.Client {
	return http.DefaultClient
}

func TestProxyClientSurvivesUnrelatedServerCleanup(t *testing.T) {
	t.Parallel()
	server, closeProxy := testProxy(t, http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = io.WriteString(w, "[]")
	}), time.Second, maxResponseBytes)
	defer closeProxy()
	client := testHTTPClient(server)
	var reused atomic.Bool
	requestOnce := func() {
		t.Helper()
		trace := &httptrace.ClientTrace{
			GotConn: func(info httptrace.GotConnInfo) { reused.Store(info.Reused) },
		}
		ctx := httptrace.WithClientTrace(context.Background(), trace)
		request, err := http.NewRequestWithContext(ctx, http.MethodGet, server.URL+"/v1.50/containers/json", nil)
		if err != nil {
			t.Fatal(err)
		}
		response, err := client.Do(request)
		if err != nil {
			t.Fatal(err)
		}
		if response == nil {
			t.Fatal("HTTP request returned a nil response")
			return
		}
		body, readErr := io.ReadAll(response.Body)
		closeErr := response.Body.Close()
		if readErr != nil || closeErr != nil || response.StatusCode != http.StatusOK || string(body) != "[]" {
			t.Fatalf("response = %d %q, read=%v close=%v", response.StatusCode, body, readErr, closeErr)
		}
	}
	requestOnce()

	// Closing an unrelated httptest server closes the global default transport.
	// This fixture's already-idle connection must belong to its own client.
	unrelated := httptest.NewServer(http.NotFoundHandler())
	unrelated.Close()
	reused.Store(false)
	requestOnce()
	if !reused.Load() {
		t.Fatal("unrelated server cleanup discarded this fixture's idle connection")
	}
}
