package handlers

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"net/http"
	"net/http/httputil"
	"regexp"
	"strings"
	"time"

	"log/slog"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	pb "github.com/university-ecosystem/core/gen/go/file_processor/v1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	grpc_health_v1 "google.golang.org/grpc/health/grpc_health_v1"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
)

// GW-P2-01 (audit Wave 10): validate X-Request-ID format to prevent log injection.
// An attacker-controlled X-Request-ID containing newlines/control characters can
// inject fake log entries into structured logging systems (Splunk, CloudWatch, etc.).
var validRequestIDRe = regexp.MustCompile(`^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$`)

// ProxyHandler creates a Gin handler that proxies requests to the backend.
//
// When internalSecret is non-empty (RZ-14-05), it HMAC-SHA256 signs the
// X-User-ID and X-Session-ID headers and forwards the digest as
// X-Internal-Signature. The backend verifies this signature before trusting
// the headers, preventing impersonation via path smuggling or SSRF.
func ProxyHandler(proxy *httputil.ReverseProxy, internalSecret []byte) gin.HandlerFunc {
	return func(c *gin.Context) {
		// Add request ID header if absent or malformed.
		// RZ-03: Use crypto-random UUID instead of timestamp prefix.
		// GW-P2-01: validate client-supplied ID against UUID format to prevent
		// log injection — a non-UUID value is silently replaced with a fresh ID.
		requestID := c.GetHeader("X-Request-ID")
		if requestID == "" || !validRequestIDRe.MatchString(requestID) {
			requestID = uuid.New().String()
		}
		c.Request.Header.Set("X-Request-ID", requestID)

		// RZ: Drop any internal auth headers from the client before proxying.
		// This ensures zero-trust between client and backend — only gateway-issued
		// headers (verified below) are forwarded.
		c.Request.Header.Del("X-User-ID")
		c.Request.Header.Del("X-Session-ID")
		c.Request.Header.Del("X-Tenant-ID")
		c.Request.Header.Del("X-Internal-Signature") // RZ-14-05: prevent client forgery

		// Inject verified identity headers from validated JWT claims.
		userIDVal, hasUser := c.Get("user_id")
		sessionIDVal, hasSession := c.Get("session_id")
		tenantIDVal, _ := c.Get("tenant_id")

		// RZ-33-23: Use two-value type assertion to avoid panic on non-string ctx values.
		userID, userOK := userIDVal.(string)
		sessionID, sessionOK := sessionIDVal.(string)
		tenantID, _ := tenantIDVal.(string)
		if hasUser && userOK {
			c.Request.Header.Set("X-User-ID", userID)
		}
		if hasSession && sessionOK {
			c.Request.Header.Set("X-Session-ID", sessionID)
		}
		if tenantID != "" {
			c.Request.Header.Set("X-Tenant-ID", tenantID)
		}

		// RZ-14-05: Sign identity headers with HMAC-SHA256 so the backend can
		// cryptographically verify that this request passed through the gateway.
		// Signature covers "{user_id}:{session_id}:{tenant_id}" (or "{user_id}:{session_id}").
		if len(internalSecret) > 0 && hasUser && userOK && hasSession && sessionOK {
			mac := hmac.New(sha256.New, internalSecret)
			if tenantID != "" {
				mac.Write([]byte(userID + ":" + sessionID + ":" + tenantID))
			} else {
				mac.Write([]byte(userID + ":" + sessionID))
			}
			c.Request.Header.Set("X-Internal-Signature", hex.EncodeToString(mac.Sum(nil)))
		}

		proxy.ServeHTTP(c.Writer, c.Request)
	}
}

// HealthHandler returns a simple OK status to indicate the gateway is running.
func HealthHandler(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{"status": "healthy", "service": "gateway"})
}

type fileProcessorHealthChecker interface {
	Check(context.Context, *grpc_health_v1.HealthCheckRequest, ...grpc.CallOption) (*grpc_health_v1.HealthCheckResponse, error)
}

// ReadinessHandler proves that the gateway's real gRPC transport can complete
// an authenticated file-processor health RPC. The request context owns the
// bounded child context, so cancellation never leaves a probe goroutine behind.
func ReadinessHandler(client fileProcessorHealthChecker, timeout time.Duration) gin.HandlerFunc {
	return func(c *gin.Context) {
		if client == nil || timeout <= 0 {
			c.JSON(http.StatusServiceUnavailable, gin.H{"status": "not_ready", "service": "gateway"})
			return
		}
		ctx, cancel := context.WithTimeout(c.Request.Context(), timeout)
		defer cancel()
		response, err := client.Check(ctx, &grpc_health_v1.HealthCheckRequest{Service: "file_processor.v1.FileProcessingService"})
		if err != nil || response.GetStatus() != grpc_health_v1.HealthCheckResponse_SERVING {
			c.JSON(http.StatusServiceUnavailable, gin.H{"status": "not_ready", "service": "gateway"})
			return
		}
		c.JSON(http.StatusOK, gin.H{"status": "ready", "service": "gateway"})
	}
}

// ProxyOrFileHandler routes /v1/files/process/sync to gRPC file-processor,
// everything else to the reverse proxy. This avoids gin wildcard route conflict
// between /v1/files/* and /v1/*path.
func ProxyOrFileHandler(proxy *httputil.ReverseProxy, internalSecret []byte, ctx context.Context, grpcConn *grpc.ClientConn, fileClient pb.FileProcessingServiceClient, logger *slog.Logger, capabilitySecrets ...[]byte) gin.HandlerFunc {
	proxyFn := ProxyHandler(proxy, internalSecret)
	fileFn := FileProcessSyncHandler(ctx, grpcConn, fileClient, logger, capabilitySecrets...)

	return func(c *gin.Context) {
		path := c.Param("path")
		if c.Request.Method == http.MethodPost && path == "/files/process/sync" {
			fileFn(c)
			return
		}
		proxyFn(c)
	}
}

// fileProcessSyncRequest is the validated HTTP representation of a synchronous
// file-processing request. Keeping it named makes the request validation and
// capability binding helpers share one exact contract.
type fileProcessSyncRequest struct {
	ID        string            `json:"id" binding:"required,uuid"`
	Type      string            `json:"type" binding:"required"`
	SourceKey string            `json:"source_key" binding:"required"`
	DestKey   string            `json:"dest_key" binding:"required"`
	Options   map[string]string `json:"options"`
}

func bindFileProcessSyncRequest(c *gin.Context) (fileProcessSyncRequest, error) {
	var req fileProcessSyncRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		return fileProcessSyncRequest{}, err
	}
	return req, nil
}

// verifyFileProcessCapability validates the trusted backend proof before any
// caller-controlled capability reaches the gRPC boundary. It also removes the
// bearer value from the HTTP request once verified so generic middleware and
// access logging cannot persist it.
func verifyFileProcessCapability(c *gin.Context, req fileProcessSyncRequest, capabilitySecrets ...[]byte) (string, bool) {
	if len(capabilitySecrets) == 0 || len(capabilitySecrets[0]) == 0 {
		return "", true
	}

	values := c.Request.Header.Values(pb.ProcessingCapabilityHeader)
	if len(values) != 1 || strings.TrimSpace(values[0]) == "" {
		c.JSON(http.StatusForbidden, gin.H{"error": "forbidden"})
		return "", false
	}
	userID, userOK := c.Get("user_id")
	sessionID, sessionOK := c.Get("session_id")
	user, userStringOK := userID.(string)
	session, sessionStringOK := sessionID.(string)
	tenant, _ := c.Get("tenant_id")
	tenantID, _ := tenant.(string)
	if !userOK || !sessionOK || !userStringOK || !sessionStringOK || user == "" || session == "" {
		c.JSON(http.StatusForbidden, gin.H{"error": "forbidden"})
		return "", false
	}

	verifiedCapability := strings.TrimSpace(values[0])
	claims, err := pb.VerifyProcessingCapability(verifiedCapability, capabilitySecrets[0], time.Now().UTC())
	if err != nil || !claims.Matches(pb.ProcessingCapabilityExpectation{
		ID:        req.ID,
		Type:      req.Type,
		SourceKey: req.SourceKey,
		DestKey:   req.DestKey,
		UserID:    user,
		SessionID: session,
		TenantID:  tenantID,
	}) {
		c.JSON(http.StatusForbidden, gin.H{"error": "forbidden"})
		return "", false
	}

	c.Request.Header.Del(pb.ProcessingCapabilityHeader)
	return verifiedCapability, true
}

func fileProcessRPCContext(c *gin.Context, verifiedCapability string) (context.Context, context.CancelFunc) {
	// Use the per-request context so cancellation propagates when the client
	// disconnects (RZ-33-04).
	rpcCtx, cancel := context.WithTimeout(c.Request.Context(), 10*time.Second)
	if authHeader := c.GetHeader("Authorization"); authHeader != "" {
		rpcCtx = metadata.AppendToOutgoingContext(rpcCtx, "authorization", authHeader)
	}
	tenantIDVal, _ := c.Get("tenant_id")
	if tenantID, ok := tenantIDVal.(string); ok && tenantID != "" {
		rpcCtx = metadata.AppendToOutgoingContext(rpcCtx, "x-tenant-id", tenantID)
	}
	if verifiedCapability != "" {
		rpcCtx = metadata.AppendToOutgoingContext(
			rpcCtx,
			strings.ToLower(pb.ProcessingCapabilityHeader),
			verifiedCapability,
		)
	}
	return rpcCtx, cancel
}

func writeFileProcessError(c *gin.Context, logger *slog.Logger, err error) {
	// PERF-W5-03: Map gRPC status codes to semantically correct HTTP codes.
	// Load balancers and monitoring treat 504 vs 500 very differently — 504
	// triggers upstream-timeout alerts and retries, 500 triggers error-rate alerts.
	switch status.Code(err) {
	case codes.DeadlineExceeded:
		logger.WarnContext(c.Request.Context(), "gRPC upstream timeout", "err", err)
		c.JSON(http.StatusGatewayTimeout, gin.H{"error": "upstream_timeout"})
	case codes.Unavailable:
		logger.WarnContext(c.Request.Context(), "gRPC upstream unavailable", "err", err)
		c.JSON(http.StatusServiceUnavailable, gin.H{"error": "upstream_unavailable"})
	case codes.PermissionDenied, codes.Unauthenticated:
		logger.WarnContext(c.Request.Context(), "gRPC permission denied", "err", err)
		c.JSON(http.StatusForbidden, gin.H{"error": "forbidden"})
	case codes.ResourceExhausted:
		logger.WarnContext(c.Request.Context(), "gRPC resource exhausted", "err", err)
		c.JSON(http.StatusTooManyRequests, gin.H{"error": "too_many_requests"})
	case codes.InvalidArgument:
		logger.WarnContext(c.Request.Context(), "gRPC invalid argument", "err", err)
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid_argument"})
	case codes.NotFound:
		logger.WarnContext(c.Request.Context(), "gRPC resource not found", "err", err)
		c.JSON(http.StatusNotFound, gin.H{"error": "not_found"})
	case codes.AlreadyExists:
		logger.WarnContext(c.Request.Context(), "gRPC resource already exists", "err", err)
		c.JSON(http.StatusConflict, gin.H{"error": "already_exists"})
	case codes.Unimplemented:
		logger.WarnContext(c.Request.Context(), "gRPC method unimplemented", "err", err)
		c.JSON(http.StatusNotImplemented, gin.H{"error": "unimplemented"})
	case codes.OK, codes.Canceled, codes.Unknown, codes.FailedPrecondition, codes.Aborted, codes.OutOfRange, codes.Internal, codes.DataLoss:
		// Fall through to the default handler for uncommon/unexpected codes.
		fallthrough
	default:
		logger.ErrorContext(c.Request.Context(), "gRPC call failed", "err", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "processing_failed"})
	}
}

// FileProcessSyncHandler proxies a synchronous file-processing request to the
// file-processor service over gRPC.
func FileProcessSyncHandler(ctx context.Context, grpcConn *grpc.ClientConn, fileClient pb.FileProcessingServiceClient, logger *slog.Logger, capabilitySecrets ...[]byte) gin.HandlerFunc {
	return func(c *gin.Context) { //nolint:contextcheck // uses c.Request.Context() for gRPC calls
		// GW-P2-02 (audit Wave 10): grpcConn.GetState() is advisory and was
		// intentionally removed; the RPC itself reports transient failures.
		if grpcConn == nil {
			c.JSON(http.StatusServiceUnavailable, gin.H{"error": "File processor unavailable"})
			return
		}

		req, err := bindFileProcessSyncRequest(c)
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}

		verifiedCapability, ok := verifyFileProcessCapability(c, req, capabilitySecrets...)
		if !ok {
			return
		}

		rpcCtx, cancel := fileProcessRPCContext(c, verifiedCapability)
		defer cancel()
		resp, err := fileClient.ProcessFile(rpcCtx, &pb.ProcessFileRequest{
			Id:        req.ID,
			Type:      req.Type,
			SourceKey: req.SourceKey,
			DestKey:   req.DestKey,
			Options:   req.Options,
		})
		if err != nil {
			writeFileProcessError(c, logger, err)
			return
		}

		c.JSON(http.StatusOK, resp)
	}
}
