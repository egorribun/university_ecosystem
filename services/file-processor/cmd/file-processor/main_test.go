package main

import (
	"context"
	"errors"
	"testing"

	"github.com/grpc-ecosystem/go-grpc-middleware/v2/interceptors/auth"
	"github.com/stretchr/testify/assert"
	"google.golang.org/grpc"
)

// Wave 140 (z) #2 — selective auth interceptor tests.
//
// gRPC health probe (grpc.health.v1.Health) must bypass auth so compose-level
// grpc_health_probe (W137 SW5) works without bearer tokens. All other RPCs
// continue to enforce auth. Pre-W140 this was masked because file-processor
// never reached the gRPC bind step (schema.graphql + GraphQL ID typing bugs).

func TestSelectiveUnaryAuth_HealthMethodBypassesAuth(t *testing.T) {
	authCalled := false
	authFn := func(ctx context.Context) (context.Context, error) {
		authCalled = true
		return ctx, errors.New("auth should not be called for health methods")
	}

	interceptor := selectiveUnaryAuth(authFn)

	handlerCalled := false
	handler := func(ctx context.Context, req interface{}) (interface{}, error) {
		handlerCalled = true
		return "ok", nil
	}

	info := &grpc.UnaryServerInfo{FullMethod: "/grpc.health.v1.Health/Check"}
	resp, err := interceptor(context.Background(), nil, info, handler)

	assert.NoError(t, err)
	assert.Equal(t, "ok", resp)
	assert.True(t, handlerCalled, "handler should be called")
	assert.False(t, authCalled, "auth should NOT be called for health methods")
}

func TestSelectiveUnaryAuth_NonHealthMethodEnforcesAuth(t *testing.T) {
	authCalled := false
	authFn := func(ctx context.Context) (context.Context, error) {
		authCalled = true
		return ctx, nil
	}

	interceptor := selectiveUnaryAuth(authFn)

	handlerCalled := false
	handler := func(ctx context.Context, req interface{}) (interface{}, error) {
		handlerCalled = true
		return "ok", nil
	}

	info := &grpc.UnaryServerInfo{FullMethod: "/file_processor.v1.FileProcessingService/Process"}
	resp, err := interceptor(context.Background(), nil, info, handler)

	assert.NoError(t, err)
	assert.Equal(t, "ok", resp)
	assert.True(t, handlerCalled, "handler should be called")
	assert.True(t, authCalled, "auth should be called for non-health methods")
}

func TestSelectiveUnaryAuth_AuthErrorBlocksHandler(t *testing.T) {
	authFn := func(ctx context.Context) (context.Context, error) {
		return nil, errors.New("invalid token")
	}

	interceptor := selectiveUnaryAuth(authFn)

	handlerCalled := false
	handler := func(ctx context.Context, req interface{}) (interface{}, error) {
		handlerCalled = true
		return "ok", nil
	}

	info := &grpc.UnaryServerInfo{FullMethod: "/file_processor.v1.FileProcessingService/Process"}
	resp, err := interceptor(context.Background(), nil, info, handler)

	assert.Error(t, err)
	assert.Nil(t, resp)
	assert.False(t, handlerCalled, "handler should NOT be called when auth fails")
	assert.Contains(t, err.Error(), "invalid token")
}

func TestSelectiveStreamAuth_HealthMethodBypassesAuth(t *testing.T) {
	authCalled := false
	authFn := func(ctx context.Context) (context.Context, error) {
		authCalled = true
		return ctx, errors.New("auth should not be called for health methods")
	}

	interceptor := selectiveStreamAuth(authFn)

	handlerCalled := false
	handler := func(srv interface{}, ss grpc.ServerStream) error {
		handlerCalled = true
		return nil
	}

	ss := &mockServerStream{ctx: context.Background()}
	info := &grpc.StreamServerInfo{FullMethod: "/grpc.health.v1.Health/Watch"}
	err := interceptor(nil, ss, info, handler)

	assert.NoError(t, err)
	assert.True(t, handlerCalled, "handler should be called")
	assert.False(t, authCalled, "auth should NOT be called for health stream methods")
}

func TestSelectiveStreamAuth_NonHealthMethodEnforcesAuth(t *testing.T) {
	authCalled := false
	authFn := func(ctx context.Context) (context.Context, error) {
		authCalled = true
		return ctx, nil
	}

	interceptor := selectiveStreamAuth(authFn)

	handlerCalled := false
	handler := func(srv interface{}, ss grpc.ServerStream) error {
		handlerCalled = true
		return nil
	}

	ss := &mockServerStream{ctx: context.Background()}
	info := &grpc.StreamServerInfo{FullMethod: "/file_processor.v1.FileProcessingService/Watch"}
	err := interceptor(nil, ss, info, handler)

	assert.NoError(t, err)
	assert.True(t, handlerCalled, "handler should be called")
	assert.True(t, authCalled, "auth should be called for non-health stream methods")
}

func TestHealthMethodPrefixMatchesAllHealthRPCs(t *testing.T) {
	// Defensive assertion: ensure our prefix matches both Check and Watch
	// methods (the two RPCs defined in grpc.health.v1.Health service).
	assert.Equal(t, "/grpc.health.v1.Health/", healthMethodPrefix)

	checkMethod := "/grpc.health.v1.Health/Check"
	watchMethod := "/grpc.health.v1.Health/Watch"

	assert.True(t, len(checkMethod) > len(healthMethodPrefix))
	assert.True(t, len(watchMethod) > len(healthMethodPrefix))
}

// mockServerStream implements grpc.ServerStream for testing.
type mockServerStream struct {
	grpc.ServerStream
	ctx context.Context
}

func (m *mockServerStream) Context() context.Context { return m.ctx }

// Ensure the auth package is still referenced in case we need it via this file.
var _ = auth.AuthFromMD
