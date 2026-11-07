package main

import (
	"context"
	"crypto/rsa"
	"io"
	"net/http"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/stretchr/testify/require"
	pb "github.com/university-ecosystem/core/gen/go/file_processor/v1"
	"github.com/university-ecosystem/file-processor/internal/config"
	"github.com/university-ecosystem/file-processor/internal/service"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
)

func aud188SignedToken(t *testing.T, key *rsa.PrivateKey, kid string, now time.Time) string {
	t.Helper()
	token := jwt.NewWithClaims(jwt.SigningMethodRS256, strictAuthClaims(now))
	token.Header["kid"] = kid
	encoded, err := token.SignedString(key)
	require.NoError(t, err)
	return encoded
}

// Exercise the actual refresh and gRPC authentication boundary without a
// network listener. The synthetic issuer keeps both keys during the transition.
func TestAUD188JWKSRefreshAuthenticatesOverlappingAndRetiredKeys(t *testing.T) {
	oldKey := generateRSAKey(t)
	newKey := generateRSAKey(t)
	oldDocument := string(marshalJWKS(t, rsaJWK("old", &oldKey.PublicKey)))
	overlapDocument := string(marshalJWKS(t, rsaJWK("old", &oldKey.PublicKey), rsaJWK("new", &newKey.PublicKey)))
	newDocument := string(marshalJWKS(t, rsaJWK("new", &newKey.PublicKey)))
	var published atomic.Value
	published.Store(oldDocument)
	client := &http.Client{Transport: roundTripFunc(func(*http.Request) (*http.Response, error) {
		return &http.Response{
			StatusCode: http.StatusOK,
			Body:       io.NopCloser(strings.NewReader(published.Load().(string))),
		}, nil
	})}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	cfg := &config.Config{
		Environment:         "production",
		JWKSURL:             "http://backend:8000/.well-known/jwks.json",
		JWKSRefreshInterval: 1,
		JWTAudience:         defaultJWTAudience,
		JWTIssuer:           "https://issuer.example",
	}
	store, err := initializeJWKSKeySet(ctx, cfg, nil, discardLogger(), client)
	require.NoError(t, err)
	options, err := strictJWTOptionsWithKeySet(cfg, nil, &revocationCheckerStub{}, store)
	require.NoError(t, err)
	interceptor := selectiveUnaryAuth(authFuncWithOptions("", nil, discardLogger(), options))
	processor := &service.Server{}
	probe := func(token string) codes.Code {
		incoming := metadata.NewIncomingContext(ctx, metadata.Pairs("authorization", "Bearer "+token))
		_, probeErr := interceptor(incoming, &pb.ProcessFileRequest{}, &grpc.UnaryServerInfo{
			FullMethod: pb.FileProcessingService_ProcessFile_FullMethodName,
		}, func(requestCtx context.Context, request any) (any, error) {
			return processor.ProcessFile(requestCtx, request.(*pb.ProcessFileRequest))
		})
		return status.Code(probeErr)
	}
	now := time.Now().UTC()
	oldToken := aud188SignedToken(t, oldKey, "old", now)
	newToken := aud188SignedToken(t, newKey, "new", now)
	forgedToken := aud188SignedToken(t, oldKey, "new", now)
	// InvalidArgument proves authentication reached the empty request's input
	// validation, before a Temporal workflow or any capability is used.
	require.Equal(t, codes.InvalidArgument, probe(oldToken))
	require.Equal(t, codes.Unauthenticated, probe(newToken))

	published.Store(overlapDocument)
	require.Eventually(t, func() bool { return probe(newToken) == codes.InvalidArgument }, 5*time.Second, 20*time.Millisecond)
	require.Equal(t, codes.InvalidArgument, probe(oldToken))
	require.Equal(t, codes.Unauthenticated, probe(forgedToken))

	// A malformed response must not displace the last valid overlap snapshot.
	published.Store("{malformed")
	require.Error(t, refreshJWKSOnce(ctx, client, cfg.JWKSURL, store))
	require.Equal(t, codes.InvalidArgument, probe(oldToken))
	require.Equal(t, codes.InvalidArgument, probe(newToken))

	published.Store(newDocument)
	require.Eventually(t, func() bool { return probe(oldToken) == codes.Unauthenticated }, 5*time.Second, 20*time.Millisecond)
	require.Equal(t, codes.InvalidArgument, probe(newToken))
}
