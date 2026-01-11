package handlers

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"net/http"
	"net/http/httputil"
	"time"

	"github.com/gin-gonic/gin"
	pb "github.com/university-ecosystem/core/gen/go/file_processor/v1"
	"go.uber.org/zap"
	"google.golang.org/grpc"
)

// ProxyHandler creates a Gin handler that proxies requests
func ProxyHandler(proxy *httputil.ReverseProxy) gin.HandlerFunc {
	return func(c *gin.Context) {
		// Add request ID header
		if c.GetHeader("X-Request-ID") == "" {
			c.Request.Header.Set("X-Request-ID", GenerateRequestID())
		}

		// Add user info from JWT to headers
		if userID, exists := c.Get("user_id"); exists {
			c.Request.Header.Set("X-User-ID", userID.(string))
		}

		proxy.ServeHTTP(c.Writer, c.Request)
	}
}

func GenerateRequestID() string {
	return time.Now().Format("20060102150405") + "-" + randomString(8)
}

func randomString(n int) string {
	b := make([]byte, n/2+1)
	if _, err := rand.Read(b); err != nil {
		return "fallback-" + time.Now().Format("150405")
	}
	return hex.EncodeToString(b)[:n]
}

func HealthHandler(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{"status": "healthy", "service": "gateway"})
}

func FileProcessSyncHandler(grpcConn *grpc.ClientConn, fileClient pb.FileProcessingServiceClient, logger *zap.Logger) gin.HandlerFunc {
	// Note: grpcMock/Interface usage would be better for testing
	// For now we pass the concrete client and connection. Or just the client if we don't need conn state.
	// However, the original code checked conn state.

	return func(c *gin.Context) {
		// We can't easily check state on the client interface without casting or passing the conn separately.
		// Assuming we pass conn.

		/*
			if grpcConn == nil || grpcConn.GetState() != connectivity.Ready && grpcConn.GetState() != connectivity.Idle {
				// Fallback or error if gRPC unavailable
				// For now, error out
				c.JSON(http.StatusServiceUnavailable, gin.H{"error": "File processor unavailable"})
				return
			}
		*/
		// Simplified: Trust the client/dialer to handle connection states or return errors.
		// If we really need state check, we pass the conn.

		var req struct {
			ID        string            `json:"id"`
			Type      string            `json:"type"`
			SourceKey string            `json:"source_key"`
			DestKey   string            `json:"dest_key"`
			Options   map[string]string `json:"options"`
		}

		if err := c.BindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}

		// Call gRPC
		rpcCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()

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
