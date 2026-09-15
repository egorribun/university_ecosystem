package handlers

import (
	"bytes"
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	pb "github.com/university-ecosystem/core/gen/go/file_processor/v1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/metadata"
)

var gatewayCapabilityKey = strings.Repeat("k", 32)

type capabilityCaptureClient struct {
	called bool
	ctx    context.Context
}

func (c *capabilityCaptureClient) ProcessFile(ctx context.Context, _ *pb.ProcessFileRequest, _ ...grpc.CallOption) (*pb.ProcessFileResponse, error) {
	c.called = true
	c.ctx = ctx
	return &pb.ProcessFileResponse{JobId: "capability-job"}, nil
}

func gatewayCapabilityToken(t *testing.T, req *pb.ProcessFileRequest, user, session string) string {
	t.Helper()
	now := time.Now().UTC()
	token, err := pb.MintProcessingCapabilityAt([]byte(gatewayCapabilityKey), pb.ProcessingCapabilityClaims{
		ID: req.Id, Type: req.Type, SourceKey: req.SourceKey, DestKey: req.DestKey,
		UserID: user, SessionID: session, ExpiresAt: now.Add(5 * time.Minute).Unix(),
		Nonce: "gateway-capability-nonce",
	}, now)
	require.NoError(t, err)
	return token
}

func TestFileProcessSyncHandler_RejectsMissingCapabilityWhenConfigured(t *testing.T) {
	client := &capabilityCaptureClient{}
	router := gin.New()
	router.POST("/sync", func(c *gin.Context) {
		c.Set("user_id", "u-1")
		c.Set("session_id", "session-1")
		c.Next()
	}, FileProcessSyncHandler(context.Background(), &grpc.ClientConn{}, client, nil, []byte(gatewayCapabilityKey)))

	request := httptest.NewRequest(http.MethodPost, "/sync", bytes.NewBufferString(`{"id":"550e8400-e29b-41d4-a716-446655440000","type":"image_resize","source_key":"users/u-1/src.png","dest_key":"users/u-1/dst.png"}`))
	request.Header.Set("Content-Type", "application/json")
	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, request)

	assert.Equal(t, http.StatusForbidden, recorder.Code)
	assert.False(t, client.called)
}

func TestFileProcessSyncHandler_ForwardsVerifiedCapabilityMetadata(t *testing.T) {
	client := &capabilityCaptureClient{}
	req := &pb.ProcessFileRequest{Id: "550e8400-e29b-41d4-a716-446655440000", Type: "image_resize", SourceKey: "users/u-1/src.png", DestKey: "users/u-1/dst.png"}
	// Build the JSON body from the exact request fields so this test exercises
	// the HTTP-to-gRPC boundary rather than a hand-written token-only path.
	token := gatewayCapabilityToken(t, req, "u-1", "session-1")
	router := gin.New()
	router.POST("/sync", func(c *gin.Context) {
		c.Set("user_id", "u-1")
		c.Set("session_id", "session-1")
		c.Next()
	}, FileProcessSyncHandler(context.Background(), &grpc.ClientConn{}, client, nil, []byte(gatewayCapabilityKey)))

	request := httptest.NewRequest(http.MethodPost, "/sync", bytes.NewBufferString(`{"id":"550e8400-e29b-41d4-a716-446655440000","type":"image_resize","source_key":"users/u-1/src.png","dest_key":"users/u-1/dst.png"}`))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set(pb.ProcessingCapabilityHeader, token)
	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, request)

	assert.Equal(t, http.StatusOK, recorder.Code)
	assert.True(t, client.called)
	md, ok := metadata.FromOutgoingContext(client.ctx)
	require.True(t, ok)
	assert.Equal(t, []string{token}, md.Get(strings.ToLower(pb.ProcessingCapabilityHeader)))
}

func TestFileProcessSyncHandler_RejectsCapabilityForDifferentIdentity(t *testing.T) {
	client := &capabilityCaptureClient{}
	req := &pb.ProcessFileRequest{Id: "550e8400-e29b-41d4-a716-446655440000", Type: "image_resize", SourceKey: "users/u-1/src.png", DestKey: "users/u-1/dst.png"}
	token := gatewayCapabilityToken(t, req, "u-1", "session-1")
	router := gin.New()
	router.POST("/sync", func(c *gin.Context) {
		c.Set("user_id", "u-2")
		c.Set("session_id", "session-2")
		c.Next()
	}, FileProcessSyncHandler(context.Background(), &grpc.ClientConn{}, client, nil, []byte(gatewayCapabilityKey)))

	request := httptest.NewRequest(http.MethodPost, "/sync", bytes.NewBufferString(`{"id":"550e8400-e29b-41d4-a716-446655440000","type":"image_resize","source_key":"users/u-1/src.png","dest_key":"users/u-1/dst.png"}`))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set(pb.ProcessingCapabilityHeader, token)
	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, request)

	assert.Equal(t, http.StatusForbidden, recorder.Code)
	assert.False(t, client.called)
}

func TestFileProcessSyncHandler_RejectsCapabilityWithoutAuthenticatedIdentity(t *testing.T) {
	client := &capabilityCaptureClient{}
	req := &pb.ProcessFileRequest{Id: "550e8400-e29b-41d4-a716-446655440000", Type: "image_resize", SourceKey: "users/u-1/src.png", DestKey: "users/u-1/dst.png"}
	token := gatewayCapabilityToken(t, req, "u-1", "session-1")
	router := gin.New()
	router.POST("/sync", FileProcessSyncHandler(context.Background(), &grpc.ClientConn{}, client, nil, []byte(gatewayCapabilityKey)))

	request := httptest.NewRequest(http.MethodPost, "/sync", bytes.NewBufferString(`{"id":"550e8400-e29b-41d4-a716-446655440000","type":"image_resize","source_key":"users/u-1/src.png","dest_key":"users/u-1/dst.png"}`))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set(pb.ProcessingCapabilityHeader, token)
	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, request)

	assert.Equal(t, http.StatusForbidden, recorder.Code)
	assert.False(t, client.called)
}
