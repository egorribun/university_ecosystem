package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"log/slog"
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"os/signal"
	"regexp"
	"strconv"
	"strings"
	"syscall"
	"time"
)

const (
	listenAddress      = ":2375"
	dockerSocketPath   = "/var/run/docker.sock"
	requestTimeout     = 15 * time.Second
	responseTimeout    = 5 * time.Second
	shutdownTimeout    = 10 * time.Second
	healthcheckTimeout = 2 * time.Second
	maxHeaderBytes     = 8 << 10
	maxQueryBytes      = 4 << 10
	maxResponseBytes   = 2 << 20
	projectLabel       = "com.docker.compose.project"
	serviceLabel       = "com.docker.compose.service"
)

var (
	containerIDPattern = regexp.MustCompile(`^[a-fA-F0-9]{12,64}$`)
	apiVersion         = regexp.MustCompile(`^v[0-9]+\.[0-9]+$`)

	signalContext = func() (context.Context, context.CancelFunc) {
		return signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	}
	listenTCP   = net.Listen
	runProcess  = run
	exitProcess = os.Exit

	// healthcheckURL stays fixed to this process's local listener in production.
	healthcheckURL = "http://127.0.0.1:2375/healthz"
)

type endpoint uint8

const (
	unknown endpoint = iota
	health
	ping
	version
	containers
	networks
	inspect
	logs
)

func main() {
	if len(os.Args) == 2 && os.Args[1] == "--healthcheck" {
		if err := runHealthcheck(); err != nil {
			slog.Error("Docker log proxy health check failed", "error", err)
			exitProcess(1)
			return
		}
		return
	}
	if err := runProcess(); err != nil {
		slog.Error("Docker log proxy stopped", "error", err)
		exitProcess(1)
	}
}

func runHealthcheck() error {
	client := newHealthcheckClient(healthcheckTimeout)
	defer client.CloseIdleConnections()
	return checkHealthEndpoint(client, healthcheckURL)
}

func newHealthcheckClient(timeout time.Duration) *http.Client {
	return &http.Client{
		Timeout:   timeout,
		Transport: &http.Transport{Proxy: nil},
		CheckRedirect: func(_ *http.Request, _ []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}
}

func checkHealthEndpoint(client *http.Client, target string) error {
	request, err := http.NewRequestWithContext(context.Background(), http.MethodGet, target, nil)
	if err != nil {
		return fmt.Errorf("create docker log proxy health request: %w", err)
	}
	response, err := client.Do(request)
	if err != nil {
		return fmt.Errorf("docker log proxy health request failed: %w", err)
	}
	if response == nil || response.Body == nil {
		return errors.New("docker log proxy health response unavailable")
	}
	closeErr := response.Body.Close()
	if response.StatusCode != http.StatusOK {
		statusErr := fmt.Errorf("docker log proxy health endpoint returned %s", response.Status)
		return errors.Join(statusErr, closeErr)
	}
	if closeErr != nil {
		return fmt.Errorf("close docker log proxy health response: %w", closeErr)
	}
	return nil
}

func run() error {
	ctx, stop := signalContext()
	defer stop()
	listener, err := listenTCP("tcp", listenAddress)
	if err != nil {
		return fmt.Errorf("listen for Docker log proxy: %w", err)
	}
	transport := &http.Transport{
		DialContext:           dialDockerSocket,
		ResponseHeaderTimeout: responseTimeout,
		IdleConnTimeout:       90 * time.Second,
		MaxIdleConns:          64,
		MaxConnsPerHost:       128,
		DisableCompression:    true,
	}
	return serve(ctx, listener, newProxy(transport, requestTimeout, maxResponseBytes))
}

func dialDockerSocket(ctx context.Context, _, _ string) (net.Conn, error) {
	return (&net.Dialer{}).DialContext(ctx, "unix", dockerSocketPath)
}

func serve(ctx context.Context, listener net.Listener, handler http.Handler) error {
	return serveWithShutdownTimeout(ctx, listener, handler, shutdownTimeout)
}

func serveWithShutdownTimeout(ctx context.Context, listener net.Listener, handler http.Handler, timeout time.Duration) error {
	server := &http.Server{
		Handler:           handler,
		ReadHeaderTimeout: 3 * time.Second,
		IdleTimeout:       30 * time.Second,
		MaxHeaderBytes:    maxHeaderBytes,
	}
	result := make(chan error, 1)
	go func() { result <- server.Serve(listener) }()
	select {
	case err := <-result:
		return err
	case <-ctx.Done():
		shutdown, cancel := gracefulShutdownContext(ctx, timeout)
		defer cancel()
		shutdownErr := server.Shutdown(shutdown)
		if shutdownErr != nil {
			closeErr := server.Close()
			serveErr := <-result
			return joinShutdownErrors(shutdownErr, closeErr, serveErr)
		}
		return unexpectedServeErrorAfterShutdown(<-result)
	}
}

func gracefulShutdownContext(ctx context.Context, timeout time.Duration) (context.Context, context.CancelFunc) {
	return context.WithTimeout(context.WithoutCancel(ctx), timeout)
}

func joinShutdownErrors(shutdownErr, closeErr, serveErr error) error {
	if errors.Is(serveErr, http.ErrServerClosed) {
		return errors.Join(shutdownErr, closeErr)
	}
	return errors.Join(shutdownErr, closeErr, serveErr)
}

func unexpectedServeErrorAfterShutdown(serveErr error) error {
	if errors.Is(serveErr, http.ErrServerClosed) {
		return nil
	}
	return serveErr
}

func newProxy(transport http.RoundTripper, timeout time.Duration, responseLimit int64) http.Handler {
	target := &url.URL{Scheme: "http", Host: "docker-engine"}
	proxy := &httputil.ReverseProxy{
		Rewrite: func(request *httputil.ProxyRequest) {
			request.SetURL(target)
			request.Out.Header = http.Header{"User-Agent": {"university-ecosystem-docker-log-proxy"}}
		},
		Transport:     transport,
		FlushInterval: -1,
		ModifyResponse: func(response *http.Response) error {
			return sanitizeResponse(response, responseLimit)
		},
		ErrorHandler: func(writer http.ResponseWriter, _ *http.Request, _ error) {
			http.Error(writer, "Docker API unavailable", http.StatusBadGateway)
		},
		ErrorLog: log.New(io.Discard, "", 0),
	}
	return http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if request.Method != http.MethodGet {
			writer.Header().Set("Allow", http.MethodGet)
			http.Error(writer, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		if request.ContentLength != 0 || len(request.TransferEncoding) != 0 || request.Body != nil && request.Body != http.NoBody {
			http.Error(writer, "request body not allowed", http.StatusBadRequest)
			return
		}
		route, err := classifyPath(request.URL)
		if err != nil {
			http.Error(writer, "invalid Docker API path", http.StatusBadRequest)
			return
		}
		if route == unknown {
			http.NotFound(writer, request)
			return
		}
		if err := validateQuery(route, request.URL.RawQuery); err != nil {
			http.Error(writer, "invalid Docker API query", http.StatusBadRequest)
			return
		}
		if route == health {
			writer.WriteHeader(http.StatusOK)
			return
		}
		if route == logs {
			proxy.ServeHTTP(writer, request)
			return
		}
		ctx, cancel := context.WithTimeout(request.Context(), timeout)
		defer cancel()
		proxy.ServeHTTP(writer, request.WithContext(ctx))
	})
}

func classifyPath(target *url.URL) (endpoint, error) {
	if err := validatePath(target); err != nil {
		return unknown, err
	}
	switch target.Path {
	case "/healthz":
		return health, nil
	case "/_ping":
		return ping, nil
	case "/version":
		return version, nil
	}
	return classifyVersionedPath(target.Path), nil
}

func validatePath(target *url.URL) error {
	path := target.Path
	if strings.Contains(path, "\\") || strings.Contains(path, "//") || strings.Contains(target.EscapedPath(), "%") {
		return errors.New("ambiguous path")
	}
	return nil
}

func classifyVersionedPath(path string) endpoint {
	parts := strings.Split(strings.TrimPrefix(path, "/"), "/")
	if len(parts) < 2 || !apiVersion.MatchString(parts[0]) {
		return unknown
	}
	return classifyResourcePath(parts)
}

func classifyResourcePath(parts []string) endpoint {
	switch {
	case len(parts) == 3 && parts[1] == "containers" && parts[2] == "json":
		return containers
	case len(parts) == 2 && parts[1] == "networks":
		return networks
	case len(parts) == 4 && parts[1] == "containers" && containerIDPattern.MatchString(parts[2]):
		return classifyContainerOperation(parts[3])
	default:
		return unknown
	}
}

func classifyContainerOperation(operation string) endpoint {
	switch operation {
	case "json":
		return inspect
	case "logs":
		return logs
	default:
		return unknown
	}
}

func validateQuery(route endpoint, raw string) error {
	if len(raw) > maxQueryBytes {
		return errors.New("query too large")
	}
	values, err := url.ParseQuery(raw)
	if err != nil {
		return errors.New("malformed query")
	}
	allowed, err := queryParametersFor(route)
	if err != nil {
		return err
	}
	for name, entries := range values {
		if !allowed[name] || len(entries) != 1 {
			return errors.New("unsupported query parameter")
		}
		if err := validateQueryValue(name, entries[0]); err != nil {
			return err
		}
	}
	return nil
}

func queryParametersFor(route endpoint) (map[string]bool, error) {
	switch route {
	case containers:
		return map[string]bool{"all": true}, nil
	case logs:
		return map[string]bool{
			"stdout": true, "stderr": true, "follow": true, "timestamps": true,
			"since": true, "tail": true,
		}, nil
	case ping, version, networks, inspect, health:
		return map[string]bool{}, nil
	case unknown:
		return nil, errors.New("unknown Docker endpoint")
	default:
		return nil, errors.New("unknown Docker endpoint")
	}
}

func validateQueryValue(name, value string) error {
	switch name {
	case "since":
		if !validSinceTimestamp(value) {
			return errors.New("invalid log timestamp")
		}
		return nil
	case "tail":
		return validateLogTail(value)
	default:
		return validateBooleanQuery(value)
	}
}

func validateLogTail(value string) error {
	if value == "" || value == "all" {
		return nil
	}
	if len(value) > 10 || !decimalDigits(value) {
		return errors.New("invalid log tail")
	}
	if _, err := strconv.ParseUint(value, 10, 32); err != nil {
		return errors.New("invalid log tail")
	}
	return nil
}

func validateBooleanQuery(value string) error {
	if value != "0" && value != "1" {
		return errors.New("invalid boolean query")
	}
	return nil
}

func validSinceTimestamp(value string) bool {
	seconds, fraction, hasFraction := strings.Cut(value, ".")
	if len(seconds) > 20 || !decimalDigits(seconds) {
		return false
	}
	if _, err := strconv.ParseInt(seconds, 10, 64); err != nil {
		return false
	}
	if !hasFraction {
		return true
	}
	return len(fraction) > 0 && len(fraction) <= 9 && decimalDigits(fraction)
}

func decimalDigits(value string) bool {
	if value == "" {
		return false
	}
	for _, character := range value {
		if character < '0' || character > '9' {
			return false
		}
	}
	return true
}

func sanitizeResponse(response *http.Response, limit int64) error {
	route, err := classifyPath(response.Request.URL)
	if err != nil || route == unknown || route == health {
		return errors.New("unexpected Docker response path")
	}
	for name := range response.Header {
		if name != "Api-Version" && name != "Docker-Experimental" && name != "Ostype" && name != "Content-Type" {
			response.Header.Del(name)
		}
	}
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return setBody(response, []byte(`{"message":"Docker API request failed"}`), "application/json")
	}
	if route == logs {
		discardTrailers(response)
		return nil
	}
	if route == ping {
		return setBody(response, nil, "")
	}
	body, err := readBody(response.Body, limit)
	response.Body = http.NoBody
	if err != nil {
		return err
	}
	projected, err := projectJSON(route, body)
	if err != nil {
		return err
	}
	return setBody(response, projected, "application/json")
}

// ReverseProxy copies response trailers after the body reaches EOF. Disconnect
// the trailer map before headers are copied, then clear its populated values as
// soon as streaming ends so no Docker metadata escapes with the log bytes.
func discardTrailers(response *http.Response) {
	response.Header.Del("Trailer")
	trailers := response.Trailer
	response.Trailer = nil
	if response.Body == nil {
		clear(trailers)
		return
	}
	response.Body = &trailerDiscardingBody{
		ReadCloser: response.Body,
		response:   response,
		trailers:   trailers,
	}
}

type trailerDiscardingBody struct {
	io.ReadCloser
	response *http.Response
	trailers http.Header
}

func (body *trailerDiscardingBody) Read(buffer []byte) (int, error) {
	count, err := body.ReadCloser.Read(buffer)
	if err != nil {
		body.clearTrailers()
	}
	return count, err
}

func (body *trailerDiscardingBody) Close() error {
	err := body.ReadCloser.Close()
	body.clearTrailers()
	return err
}

func (body *trailerDiscardingBody) clearTrailers() {
	clear(body.trailers)
	clear(body.response.Trailer)
	body.response.Trailer = nil
}

func readBody(body io.ReadCloser, limit int64) ([]byte, error) {
	if body == nil {
		return nil, errors.New("docker metadata response unavailable or too large")
	}
	var data []byte
	var readErr error
	if limit < 0 {
		readErr = errors.New("negative response limit")
	} else {
		data, readErr = io.ReadAll(io.LimitReader(body, limit+1))
		if readErr == nil && int64(len(data)) > limit {
			readErr = errors.New("docker metadata response too large")
		}
	}
	closeErr := body.Close()
	if readErr != nil || closeErr != nil {
		return nil, errors.Join(readErr, closeErr)
	}
	return data, nil
}

func setBody(response *http.Response, data []byte, contentType string) error {
	if response.Body != nil {
		body := response.Body
		response.Body = http.NoBody
		if err := body.Close(); err != nil {
			return fmt.Errorf("close docker response body: %w", err)
		}
	}
	response.Body = io.NopCloser(bytes.NewReader(data))
	response.ContentLength = int64(len(data))
	response.TransferEncoding = nil
	response.Trailer = nil
	response.Header.Set("Content-Length", strconv.Itoa(len(data)))
	if contentType == "" {
		response.Header.Del("Content-Type")
	} else {
		response.Header.Set("Content-Type", contentType)
	}
	return nil
}

func projectJSON(route endpoint, body []byte) ([]byte, error) {
	switch route {
	case version:
		var result struct {
			APIVersion    string `json:"ApiVersion"`
			MinAPIVersion string `json:"MinAPIVersion"`
		}
		if err := json.Unmarshal(body, &result); err != nil {
			return nil, errors.New("invalid Docker version response")
		}
		return json.Marshal(result)
	case containers:
		var result []containerSummary
		if err := json.Unmarshal(body, &result); err != nil {
			return nil, errors.New("invalid Docker container list")
		}
		for index := range result {
			result[index].Labels = composeLabels(result[index].Labels)
		}
		return json.Marshal(result)
	case networks:
		var result []networkSummary
		if err := json.Unmarshal(body, &result); err != nil {
			return nil, errors.New("invalid Docker network list")
		}
		for index := range result {
			result[index].Labels = composeLabels(result[index].Labels)
		}
		return json.Marshal(result)
	case inspect:
		var result struct {
			ID     string `json:"Id"`
			Config struct {
				TTY bool `json:"Tty"`
			} `json:"Config"`
			State struct {
				Running    bool   `json:"Running"`
				FinishedAt string `json:"FinishedAt"`
			} `json:"State"`
		}
		if err := json.Unmarshal(body, &result); err != nil {
			return nil, errors.New("invalid Docker inspect response")
		}
		return json.Marshal(result)
	case unknown, health, ping, logs:
		return nil, errors.New("unsupported Docker response")
	default:
		return nil, errors.New("unsupported Docker response")
	}
}

type containerSummary struct {
	ID              string                       `json:"Id"`
	Names           []string                     `json:"Names"`
	Labels          map[string]string            `json:"Labels"`
	HostConfig      struct{ NetworkMode string } `json:"HostConfig"`
	NetworkSettings struct {
		Networks map[string]struct {
			NetworkID string `json:"NetworkID"`
			IPAddress string `json:"IPAddress"`
		}
	} `json:"NetworkSettings"`
	Ports []struct {
		IP          string `json:"IP,omitempty"`
		PrivatePort uint16 `json:"PrivatePort"`
		PublicPort  uint16 `json:"PublicPort,omitempty"`
		Type        string `json:"Type"`
	} `json:"Ports"`
}

type networkSummary struct {
	ID       string            `json:"Id"`
	Name     string            `json:"Name"`
	Scope    string            `json:"Scope"`
	Internal bool              `json:"Internal"`
	Ingress  bool              `json:"Ingress"`
	Labels   map[string]string `json:"Labels"`
}

func composeLabels(labels map[string]string) map[string]string {
	result := make(map[string]string, 2)
	for _, name := range []string{projectLabel, serviceLabel} {
		if value, ok := labels[name]; ok {
			result[name] = value
		}
	}
	return result
}
