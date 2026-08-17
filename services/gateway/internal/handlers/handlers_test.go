package handlers

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"net/http/httputil"
	"net/url"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/assert"
	pb "github.com/university-ecosystem/core/gen/go/file_processor/v1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
)

type closeNotifyingRecorder struct {
	*httptest.ResponseRecorder
	closed chan bool
}

func (c *closeNotifyingRecorder) CloseNotify() <-chan bool {
	return c.closed
}

func newCloseNotifyingRecorder() *closeNotifyingRecorder {
	return &closeNotifyingRecorder{
		ResponseRecorder: httptest.NewRecorder(),
		closed:           make(chan bool, 1),
	}
}

func init() {
	gin.SetMode(gin.TestMode)
}

func TestHealthHandler_ReturnsOKStatus(t *testing.T) {
	router := gin.New()
	router.GET("/health", HealthHandler)

	request := httptest.NewRequestWithContext(context.Background(), http.MethodGet, "/health", nil)
	recorder := httptest.NewRecorder()

	router.ServeHTTP(recorder, request)

	assert.Equal(t, http.StatusOK, recorder.Code)
}

func TestHealthHandler_ReturnsCorrectJSON(t *testing.T) {
	router := gin.New()
	router.GET("/health", HealthHandler)

	request := httptest.NewRequestWithContext(context.Background(), http.MethodGet, "/health", nil)
	recorder := httptest.NewRecorder()

	router.ServeHTTP(recorder, request)

	body := recorder.Body.String()
	assert.Contains(t, body, `"status":"healthy"`)
	assert.Contains(t, body, `"service":"gateway"`)
}

func TestProxyHandler_SetsRequestIDHeader(t *testing.T) {
	backendServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requestID := r.Header.Get("X-Request-ID")
		assert.NotEmpty(t, requestID)
		w.WriteHeader(http.StatusOK)
	}))
	defer backendServer.Close()

	proxy := createTestProxy(backendServer.URL)
	router := gin.New()
	router.GET("/api/*path", ProxyHandler(proxy, nil))

	request := httptest.NewRequestWithContext(context.Background(), http.MethodGet, "/api/test", nil)
	recorder := newCloseNotifyingRecorder()

	router.ServeHTTP(recorder, request)

	assert.Equal(t, http.StatusOK, recorder.Code)
}

func TestProxyHandler_PreservesExistingRequestID(t *testing.T) {
	// Must be a valid UUID v4 (lowercase hex) — the handler replaces non-UUID values.
	existingID := "550e8400-e29b-41d4-a716-446655440000"
	var capturedID string

	backendServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		capturedID = r.Header.Get("X-Request-ID")
		w.WriteHeader(http.StatusOK)
	}))
	defer backendServer.Close()

	proxy := createTestProxy(backendServer.URL)
	router := gin.New()
	router.GET("/api/*path", ProxyHandler(proxy, nil))

	request := httptest.NewRequestWithContext(context.Background(), http.MethodGet, "/api/test", nil)
	request.Header.Set("X-Request-ID", existingID)
	recorder := newCloseNotifyingRecorder()

	router.ServeHTTP(recorder, request)

	assert.Equal(t, existingID, capturedID)
}

func TestProxyHandler_AddsUserIDHeader(t *testing.T) {
	var capturedUserID string

	backendServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		capturedUserID = r.Header.Get("X-User-ID")
		w.WriteHeader(http.StatusOK)
	}))
	defer backendServer.Close()

	proxy := createTestProxy(backendServer.URL)
	router := gin.New()
	router.GET("/api/*path", func(c *gin.Context) {
		c.Set("user_id", "user-456")
		c.Next()
	}, ProxyHandler(proxy, nil))

	request := httptest.NewRequestWithContext(context.Background(), http.MethodGet, "/api/test", nil)
	recorder := newCloseNotifyingRecorder()

	router.ServeHTTP(recorder, request)

	assert.Equal(t, "user-456", capturedUserID)
}

// TestProxyHandler_SetsInternalSignature verifies that when an HMAC secret is
// configured, ProxyHandler computes X-Internal-Signature as
// HMAC-SHA256("{user_id}:{session_id}") and that client-supplied forgeries are
// stripped before a fresh signature is added. (RZ-14-05)
func TestProxyHandler_SetsInternalSignature(t *testing.T) {
	const (
		testUserID    = "550e8400-e29b-41d4-a716-446655440000"
		testSessionID = "session-jti-abc123"
	)
	secret := []byte("test-internal-hmac-secret-32bytes!")

	var capturedSig, capturedUserID, capturedSessionID string
	backendServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		capturedSig = r.Header.Get("X-Internal-Signature")
		capturedUserID = r.Header.Get("X-User-ID")
		capturedSessionID = r.Header.Get("X-Session-ID")
		w.WriteHeader(http.StatusOK)
	}))
	defer backendServer.Close()

	proxy := createTestProxy(backendServer.URL)
	router := gin.New()
	router.GET("/api/*path", func(c *gin.Context) {
		c.Set("user_id", testUserID)
		c.Set("session_id", testSessionID)
		c.Next()
	}, ProxyHandler(proxy, secret))

	// Attempt to forge signature — must be replaced with the real one.
	request := httptest.NewRequestWithContext(context.Background(), http.MethodGet, "/api/test", nil)
	request.Header.Set("X-Internal-Signature", "forged-signature")
	recorder := newCloseNotifyingRecorder()

	router.ServeHTTP(recorder, request)

	assert.Equal(t, http.StatusOK, recorder.Code)
	assert.Equal(t, testUserID, capturedUserID)
	assert.Equal(t, testSessionID, capturedSessionID)

	// Compute expected HMAC-SHA256 independently.
	mac := hmac.New(sha256.New, secret)
	mac.Write([]byte(testUserID + ":" + testSessionID))
	expected := hex.EncodeToString(mac.Sum(nil))
	assert.Equal(t, expected, capturedSig, "X-Internal-Signature must be HMAC-SHA256 of user_id:session_id")
}

func TestProxyHandler_SetsTenantIdentityAndSignature(t *testing.T) {
	const (
		testUserID    = "550e8400-e29b-41d4-a716-446655440000"
		testSessionID = "session-jti-tenant"
		testTenantID  = "tenant-42"
	)
	secret := []byte("test-internal-hmac-secret-32bytes!")
	var capturedTenantID, capturedSignature string

	backendServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		capturedTenantID = r.Header.Get("X-Tenant-ID")
		capturedSignature = r.Header.Get("X-Internal-Signature")
		w.WriteHeader(http.StatusOK)
	}))
	defer backendServer.Close()

	router := gin.New()
	router.GET("/api/*path", func(c *gin.Context) {
		c.Set("user_id", testUserID)
		c.Set("session_id", testSessionID)
		c.Set("tenant_id", testTenantID)
		c.Next()
	}, ProxyHandler(createTestProxy(backendServer.URL), secret))

	recorder := newCloseNotifyingRecorder()
	router.ServeHTTP(
		recorder,
		httptest.NewRequestWithContext(context.Background(), http.MethodGet, "/api/test", nil),
	)

	mac := hmac.New(sha256.New, secret)
	_, _ = mac.Write([]byte(testUserID + ":" + testSessionID + ":" + testTenantID))
	assert.Equal(t, testTenantID, capturedTenantID)
	assert.Equal(t, hex.EncodeToString(mac.Sum(nil)), capturedSignature)
}

// TestProxyHandler_NoSignatureWithoutSecret ensures X-Internal-Signature is
// NOT set when no HMAC secret is configured (dev mode).
func TestProxyHandler_NoSignatureWithoutSecret(t *testing.T) {
	var capturedSig string
	backendServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		capturedSig = r.Header.Get("X-Internal-Signature")
		w.WriteHeader(http.StatusOK)
	}))
	defer backendServer.Close()

	proxy := createTestProxy(backendServer.URL)
	router := gin.New()
	router.GET("/api/*path", func(c *gin.Context) {
		c.Set("user_id", "some-user")
		c.Set("session_id", "some-session")
		c.Next()
	}, ProxyHandler(proxy, nil))

	request := httptest.NewRequestWithContext(context.Background(), http.MethodGet, "/api/test", nil)
	recorder := newCloseNotifyingRecorder()
	router.ServeHTTP(recorder, request)

	assert.Empty(t, capturedSig, "X-Internal-Signature must not be set when HMAC secret is empty")
}

// TestProxyHandler_DropsForgedSignatureWhenNoSecret ensures that a client-supplied
// X-Internal-Signature is deleted even when the gateway has no secret configured.
func TestProxyHandler_DropsForgedSignatureWhenNoSecret(t *testing.T) {
	var capturedSig string
	backendServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		capturedSig = r.Header.Get("X-Internal-Signature")
		w.WriteHeader(http.StatusOK)
	}))
	defer backendServer.Close()

	proxy := createTestProxy(backendServer.URL)
	router := gin.New()
	router.GET("/api/*path", ProxyHandler(proxy, nil))

	request := httptest.NewRequestWithContext(context.Background(), http.MethodGet, "/api/test", nil)
	request.Header.Set("X-Internal-Signature", "attacker-forged")
	recorder := newCloseNotifyingRecorder()
	router.ServeHTTP(recorder, request)

	assert.Empty(t, capturedSig, "Client-supplied X-Internal-Signature must always be stripped")
}

func createTestProxy(targetURL string) *httputil.ReverseProxy {
	target, err := url.Parse(targetURL)
	if err != nil {
		panic(fmt.Sprintf("failed to parse test backend URL: %v", err))
	}
	return httputil.NewSingleHostReverseProxy(target)
}

type mockFileProcessingServiceClient struct {
	resp *pb.ProcessFileResponse
	err  error
}

func newRequestWithChildContext(t *testing.T, parent context.Context, method, target string, body io.Reader) *http.Request {
	t.Helper()
	reqCtx, cancel := context.WithCancel(parent)
	t.Cleanup(cancel)
	return httptest.NewRequestWithContext(reqCtx, method, target, body)
}

func (m *mockFileProcessingServiceClient) ProcessFile(ctx context.Context, in *pb.ProcessFileRequest, opts ...grpc.CallOption) (*pb.ProcessFileResponse, error) {
	return m.resp, m.err
}

func TestFileProcessSyncHandler_Errors(t *testing.T) {
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	ctx := context.Background()

	t.Run("nil_conn", func(t *testing.T) {
		router := gin.New()
		router.POST("/sync", FileProcessSyncHandler(ctx, nil, nil, logger))

		w := httptest.NewRecorder()
		req := newRequestWithChildContext(t, ctx, http.MethodPost, "/sync", bytes.NewReader([]byte("{}")))
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusServiceUnavailable, w.Code)
		assert.Contains(t, w.Body.String(), "unavailable")
	})

	t.Run("invalid_json", func(t *testing.T) {
		dummyConn := &grpc.ClientConn{}
		router := gin.New()
		router.POST("/sync", FileProcessSyncHandler(ctx, dummyConn, nil, logger))

		w := httptest.NewRecorder()
		req := newRequestWithChildContext(t, ctx, http.MethodPost, "/sync", bytes.NewReader([]byte("{invalid-json}")))
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusBadRequest, w.Code)
	})

	t.Run("success", func(t *testing.T) {
		dummyConn := &grpc.ClientConn{}
		mockClient := &mockFileProcessingServiceClient{
			resp: &pb.ProcessFileResponse{
				JobId:   "test-id",
				DestKey: "output/done.png",
			},
		}
		router := gin.New()
		router.POST("/sync", func(c *gin.Context) {
			c.Set("tenant_id", "tenant-from-context")
			c.Next()
		}, FileProcessSyncHandler(ctx, dummyConn, mockClient, logger))

		w := httptest.NewRecorder()
		reqBody := `{"id":"550e8400-e29b-41d4-a716-446655440000","type":"resize","source_key":"in.png","dest_key":"out.png"}`
		req := newRequestWithChildContext(t, ctx, http.MethodPost, "/sync", bytes.NewReader([]byte(reqBody)))
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("Authorization", "Bearer test-token")
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusOK, w.Code)
		assert.Contains(t, w.Body.String(), "output/done.png")
	})

	t.Run("grpc_status_mapping", func(t *testing.T) {
		cases := []struct {
			grpcCode codes.Code
			wantHTTP int
			wantMsg  string
		}{
			{codes.DeadlineExceeded, http.StatusGatewayTimeout, "upstream_timeout"},
			{codes.Unavailable, http.StatusServiceUnavailable, "upstream_unavailable"},
			{codes.PermissionDenied, http.StatusForbidden, "forbidden"},
			{codes.Unauthenticated, http.StatusForbidden, "forbidden"},
			{codes.ResourceExhausted, http.StatusTooManyRequests, "too_many_requests"},
			{codes.InvalidArgument, http.StatusBadRequest, "invalid_argument"},
			{codes.NotFound, http.StatusNotFound, "not_found"},
			{codes.AlreadyExists, http.StatusConflict, "already_exists"},
			{codes.Unimplemented, http.StatusNotImplemented, "unimplemented"},
			{codes.Internal, http.StatusInternalServerError, "processing_failed"},
		}

		for _, tc := range cases {
			t.Run(fmt.Sprintf("code_%s", tc.grpcCode), func(t *testing.T) {
				dummyConn := &grpc.ClientConn{}
				mockClient := &mockFileProcessingServiceClient{
					err: status.Error(tc.grpcCode, "some grpc error"),
				}
				router := gin.New()
				router.POST("/sync", FileProcessSyncHandler(ctx, dummyConn, mockClient, logger))

				w := httptest.NewRecorder()
				reqBody := `{"id":"550e8400-e29b-41d4-a716-446655440000","type":"resize","source_key":"in.png","dest_key":"out.png"}`
				req := newRequestWithChildContext(t, ctx, http.MethodPost, "/sync", bytes.NewReader([]byte(reqBody)))
				req.Header.Set("Content-Type", "application/json")
				router.ServeHTTP(w, req)

				assert.Equal(t, tc.wantHTTP, w.Code)
				assert.Contains(t, w.Body.String(), tc.wantMsg)
			})
		}
	})

	t.Run("non_grpc_error", func(t *testing.T) {
		dummyConn := &grpc.ClientConn{}
		mockClient := &mockFileProcessingServiceClient{
			err: errors.New("raw non-grpc error"),
		}
		router := gin.New()
		router.POST("/sync", FileProcessSyncHandler(ctx, dummyConn, mockClient, logger))

		w := httptest.NewRecorder()
		reqBody := `{"id":"550e8400-e29b-41d4-a716-446655440000","type":"resize","source_key":"in.png","dest_key":"out.png"}`
		req := newRequestWithChildContext(t, ctx, http.MethodPost, "/sync", bytes.NewReader([]byte(reqBody)))
		req.Header.Set("Content-Type", "application/json")
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusInternalServerError, w.Code)
		assert.Contains(t, w.Body.String(), "processing_failed")
	})
}

// spyFileProcessingClient wraps mockFileProcessingServiceClient to record whether
// ProcessFile was invoked, so the dispatch test can assert which branch of
// ProxyOrFileHandler fired without standing up a real gRPC server.
type spyFileProcessingClient struct {
	mock   *mockFileProcessingServiceClient
	called *bool
}

func (s *spyFileProcessingClient) ProcessFile(ctx context.Context, in *pb.ProcessFileRequest, opts ...grpc.CallOption) (*pb.ProcessFileResponse, error) {
	if s.called != nil {
		*s.called = true
	}
	return s.mock.ProcessFile(ctx, in, opts...)
}

// TestProxyOrFileHandler_Dispatch verifies the router/dispatch decision in
// ProxyOrFileHandler (handlers.go:93-100): only POST /v1/files/process/sync is
// routed to the gRPC file handler; every other method/path falls through to the
// reverse proxy. The gRPC handler body itself is covered by
// TestFileProcessSyncHandler_Errors — here we exercise only the dispatch branch.
func TestProxyOrFileHandler_Dispatch(t *testing.T) {
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	ctx := context.Background()

	const proxySentinelStatus = http.StatusTeapot // 418 — unmistakable proxy sentinel
	const proxySentinelBody = "proxied-ok"

	// There's no injectable proxyFn in ProxyOrFileHandler, so the proxy "spy" must
	// be a real httptest backend behind createTestProxy. It records the hit and
	// returns a sentinel status so we can assert status passthrough.
	newRouter := func(proxyCalled, grpcCalled *bool) *gin.Engine {
		backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			*proxyCalled = true
			w.WriteHeader(proxySentinelStatus)
			if _, err := w.Write([]byte(proxySentinelBody)); err != nil {
				t.Errorf("backend write failed: %v", err)
			}
		}))
		t.Cleanup(backend.Close)

		proxy := createTestProxy(backend.URL)
		grpcMock := &spyFileProcessingClient{
			mock:   &mockFileProcessingServiceClient{resp: &pb.ProcessFileResponse{JobId: "dispatch-job", DestKey: "out.png"}},
			called: grpcCalled,
		}
		dummyConn := &grpc.ClientConn{} // non-nil to pass the grpcConn==nil guard

		r := gin.New()
		// The /v1/*path wildcard makes c.Param("path") resolve to the captured
		// suffix (handlers.go:94). Any() registers the handler for all verbs.
		r.Any("/v1/*path", ProxyOrFileHandler(proxy, nil, ctx, dummyConn, grpcMock, logger))
		return r
	}

	t.Run("GET any path routes to proxy", func(t *testing.T) {
		var proxyCalled, grpcCalled bool
		router := newRouter(&proxyCalled, &grpcCalled)

		w := newCloseNotifyingRecorder()
		req := httptest.NewRequestWithContext(context.Background(), http.MethodGet, "/v1/files/process/sync", nil)
		router.ServeHTTP(w, req)

		// Even on the file path, a GET fails the method guard → proxy branch.
		assert.True(t, proxyCalled, "GET must route to the reverse proxy")
		assert.False(t, grpcCalled, "gRPC handler must not fire for GET")
		assert.Equal(t, proxySentinelStatus, w.Code, "proxy backend status must pass through")
		assert.Contains(t, w.Body.String(), proxySentinelBody)
	})

	t.Run("POST non-file path routes to proxy", func(t *testing.T) {
		var proxyCalled, grpcCalled bool
		router := newRouter(&proxyCalled, &grpcCalled)

		w := newCloseNotifyingRecorder()
		req := httptest.NewRequestWithContext(context.Background(), http.MethodPost, "/v1/other/endpoint", bytes.NewReader([]byte("{}")))
		req.Header.Set("Content-Type", "application/json")
		router.ServeHTTP(w, req)

		// path == "/other/endpoint" != "/files/process/sync" → proxy branch.
		assert.True(t, proxyCalled, "POST to a non-file path must route to the reverse proxy")
		assert.False(t, grpcCalled, "gRPC handler must not fire for a non-file POST path")
		assert.Equal(t, proxySentinelStatus, w.Code, "proxy backend status must pass through")
		assert.Contains(t, w.Body.String(), proxySentinelBody)
	})

	t.Run("POST files process sync routes to gRPC", func(t *testing.T) {
		var proxyCalled, grpcCalled bool
		router := newRouter(&proxyCalled, &grpcCalled)

		w := newCloseNotifyingRecorder()
		reqBody := `{"id":"550e8400-e29b-41d4-a716-446655440000","type":"resize","source_key":"in.png","dest_key":"out.png"}`
		req := httptest.NewRequestWithContext(context.Background(), http.MethodPost, "/v1/files/process/sync", bytes.NewReader([]byte(reqBody)))
		req.Header.Set("Content-Type", "application/json")
		router.ServeHTTP(w, req)

		// method==POST && path=="/files/process/sync" → gRPC branch (handlers.go:95-98).
		assert.True(t, grpcCalled, "POST /v1/files/process/sync must route to the gRPC file handler")
		assert.False(t, proxyCalled, "reverse proxy must not fire for the file-process path")
		assert.Equal(t, http.StatusOK, w.Code)
		assert.Contains(t, w.Body.String(), "out.png")
	})
}

func TestFileProcessSyncHandler_ReturnsServiceUnavailableWhenGrpcConnNil(t *testing.T) {
	router := gin.New()
	logger := slog.New(slog.NewJSONHandler(io.Discard, nil))
	router.POST("/sync", FileProcessSyncHandler(context.Background(), nil, nil, logger))

	reqBody := `{"id":"550e8400-e29b-41d4-a716-446655440000","type":"resize","source_key":"in.png","dest_key":"out.png"}`
	req := httptest.NewRequestWithContext(context.Background(), http.MethodPost, "/sync", bytes.NewReader([]byte(reqBody)))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	assert.Equal(t, http.StatusServiceUnavailable, w.Code)
	assert.Contains(t, w.Body.String(), "File processor unavailable")
}

func TestFileProcessSyncHandler_PropagatesAuthorizationHeader(t *testing.T) {
	var capturedCtx context.Context
	mockClient := &mockFileProcessingServiceClient{
		resp: &pb.ProcessFileResponse{JobId: "auth-job"},
	}
	router := gin.New()
	logger := slog.New(slog.NewJSONHandler(io.Discard, nil))
	dummyConn := &grpc.ClientConn{}

	clientMock := &mockFileProcessingClientWithCtx{
		mockClient: mockClient,
		onCall: func(ctx context.Context) {
			capturedCtx = ctx
		},
	}

	router.POST("/sync", FileProcessSyncHandler(context.Background(), dummyConn, clientMock, logger))

	reqBody := `{"id":"550e8400-e29b-41d4-a716-446655440000","type":"resize","source_key":"in.png","dest_key":"out.png"}`
	req := httptest.NewRequestWithContext(context.Background(), http.MethodPost, "/sync", bytes.NewReader([]byte(reqBody)))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer test-token-123")
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	assert.Equal(t, http.StatusOK, w.Code)
	assert.NotNil(t, capturedCtx)
	md, ok := metadata.FromOutgoingContext(capturedCtx)
	assert.True(t, ok)
	authHeaders := md.Get("authorization")
	assert.Len(t, authHeaders, 1)
	assert.Equal(t, "Bearer test-token-123", authHeaders[0])
}

func TestFileProcessSyncHandler_RejectsUntrustedTenantHeaderFallback(t *testing.T) {
	var capturedCtx context.Context
	clientMock := &mockFileProcessingClientWithCtx{
		mockClient: &mockFileProcessingServiceClient{
			resp: &pb.ProcessFileResponse{JobId: "tenant-header-job"},
		},
		onCall: func(ctx context.Context) {
			capturedCtx = ctx
		},
	}

	router := gin.New()
	router.POST("/sync", FileProcessSyncHandler(
		context.Background(),
		&grpc.ClientConn{},
		clientMock,
		slog.New(slog.NewJSONHandler(io.Discard, nil)),
	))

	reqBody := `{"id":"550e8400-e29b-41d4-a716-446655440000","type":"resize","source_key":"in.png","dest_key":"out.png"}`
	req := httptest.NewRequestWithContext(
		context.Background(),
		http.MethodPost,
		"/sync",
		bytes.NewReader([]byte(reqBody)),
	)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Tenant-ID", "tenant-from-header")
	recorder := httptest.NewRecorder()

	router.ServeHTTP(recorder, req)

	assert.Equal(t, http.StatusOK, recorder.Code)
	md, _ := metadata.FromOutgoingContext(capturedCtx)
	assert.Empty(t, md.Get("x-tenant-id"))
}

type mockFileProcessingClientWithCtx struct {
	mockClient *mockFileProcessingServiceClient
	onCall     func(context.Context)
}

func (m *mockFileProcessingClientWithCtx) ProcessFile(ctx context.Context, in *pb.ProcessFileRequest, opts ...grpc.CallOption) (*pb.ProcessFileResponse, error) {
	m.onCall(ctx)
	return m.mockClient.ProcessFile(ctx, in, opts...)
}
