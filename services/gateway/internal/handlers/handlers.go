package handlers

import (
	"context"
	"net/http"
	"net/http/httputil"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	pb "github.com/university-ecosystem/core/gen/go/file_processor/v1"
	"go.uber.org/zap"
	"google.golang.org/grpc"
	"google.golang.org/grpc/connectivity"
	"google.golang.org/grpc/metadata"
)

// ProxyHandler creates a Gin handler that proxies requests
func ProxyHandler(proxy *httputil.ReverseProxy) gin.HandlerFunc {
	return func(c *gin.Context) {
		// Add request ID header if absent.
		// RZ-03: Use crypto-random UUID instead of timestamp prefix — predictable
		// timestamps in IDs enable timing correlation and replay window estimation.
		if c.GetHeader("X-Request-ID") == "" {
			c.Request.Header.Set("X-Request-ID", uuid.New().String())
		}

		// Add user info from JWT to headers
		if userID, exists := c.Get("user_id"); exists {
			c.Request.Header.Set("X-User-ID", userID.(string))
		}

		proxy.ServeHTTP(c.Writer, c.Request)
	}
}

// GenerateRequestID returns a cryptographically random UUID v4.
//
// RZ-03 (audit 2026-03-04): The previous implementation prefixed the current
// timestamp, making request IDs partially predictable and leaking server time
// to API consumers.  A full UUID provides 122 bits of entropy with no timing
// information.
func GenerateRequestID() string {
	return uuid.New().String()
}

func HealthHandler(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{"status": "healthy", "service": "gateway"})
}

func FileProcessSyncHandler(grpcConn *grpc.ClientConn, fileClient pb.FileProcessingServiceClient, logger *zap.Logger) gin.HandlerFunc {
	return func(c *gin.Context) {
		// RZ-04 (audit 2026-03-04): Restore gRPC connectivity state check.
		// The previous implementation had this guard commented out, causing the
		// gateway to forward requests to an unavailable file-processor and return
		// a generic 500 instead of a semantically correct 503 ServiceUnavailable.
		if grpcConn == nil {
			c.JSON(http.StatusServiceUnavailable, gin.H{"error": "File processor unavailable"})
			return
		}
		state := grpcConn.GetState()
		if state != connectivity.Ready && state != connectivity.Idle {
			c.JSON(http.StatusServiceUnavailable, gin.H{"error": "File processor unavailable"})
			return
		}

		var req struct {
			ID        string            `json:"id" binding:"required,uuid"`
			Type      string            `json:"type" binding:"required"`
			SourceKey string            `json:"source_key" binding:"required"`
			DestKey   string            `json:"dest_key" binding:"required"`
			Options   map[string]string `json:"options"`
		}

		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}

		// Call gRPC
		rpcCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()

		// Propagate Authorization header to gRPC metadata
		if authHeader := c.GetHeader("Authorization"); authHeader != "" {
			rpcCtx = metadata.AppendToOutgoingContext(rpcCtx, "authorization", authHeader)
		}

		resp, err := fileClient.ProcessFile(rpcCtx, &pb.ProcessFileRequest{
			Id:        req.ID,
			Type:      req.Type,
			SourceKey: req.SourceKey,
			DestKey:   req.DestKey,
			Options:   req.Options,
		})

		if err != nil {
			logger.Error("gRPC call failed", zap.Error(err))
			c.JSON(http.StatusInternalServerError, gin.H{"error": "Processing failed"})
			return
		}

		c.JSON(http.StatusOK, resp)
	}
}
