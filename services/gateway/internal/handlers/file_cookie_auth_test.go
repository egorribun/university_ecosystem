package handlers

import (
	"bytes"
	"context"
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/pem"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/require"
	pb "github.com/university-ecosystem/core/gen/go/file_processor/v1"
	"github.com/university-ecosystem/gateway/middleware"
	"google.golang.org/grpc"
	"google.golang.org/grpc/metadata"
)

func TestFileRPCForwardsMiddlewareSelectedCredential(t *testing.T) {
	privateKey, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)
	publicDER, err := x509.MarshalPKIXPublicKey(&privateKey.PublicKey)
	require.NoError(t, err)
	publicPEM := string(pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: publicDER}))
	signToken := func(user, session string) string {
		token, err := jwt.NewWithClaims(jwt.SigningMethodRS256, middleware.Claims{
			RegisteredClaims: jwt.RegisteredClaims{
				Issuer:    middleware.DefaultJWTIssuer,
				Audience:  jwt.ClaimStrings{middleware.DefaultJWTAudience},
				ID:        session,
				IssuedAt:  jwt.NewNumericDate(time.Now()),
				ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Minute)),
			},
			UserID: user, IsActive: true,
		}).SignedString(privateKey)
		require.NoError(t, err)
		return token
	}
	tokenA := signToken("user-a", "session-a")
	tokenB := signToken("user-b", "session-b")
	for _, testCase := range []struct {
		name    string
		cookie  string
		header  string
		revoked bool
		status  int
	}{
		{name: "cookie only", cookie: tokenA, status: http.StatusOK},
		{name: "header only", header: "Bearer " + tokenA, status: http.StatusOK},
		{name: "cookie wins conflicting header", cookie: tokenA, header: "Bearer " + tokenB, status: http.StatusOK},
		{name: "empty cookie falls back", header: "Bearer " + tokenA, status: http.StatusOK},
		{name: "invalid cookie never falls back", cookie: "not-a-jwt", header: "Bearer " + tokenA, status: http.StatusUnauthorized},
		{name: "revoked cookie never falls back", cookie: tokenA, header: "Bearer " + tokenB, revoked: true, status: http.StatusUnauthorized},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			mr := miniredis.RunT(t)
			rc := redis.NewClient(&redis.Options{Addr: mr.Addr()})
			t.Cleanup(func() { require.NoError(t, rc.Close()) })
			if testCase.revoked {
				require.NoError(t, mr.Set("revoked:jti:session-a", "1"))
			}
			authMiddleware := middleware.NewJWTMiddlewareWithConfig(
				"", publicPEM, rc, middleware.DefaultL1CacheConfig(),
			)
			client := &capabilityCaptureClient{}
			processRequest := &pb.ProcessFileRequest{
				Id: "550e8400-e29b-41d4-a716-446655440000", Type: "image_resize",
				SourceKey: "users/user-a/source.png", DestKey: "users/user-a/dest.png",
			}
			capability := gatewayCapabilityToken(t, processRequest, "user-a", "session-a")
			router := gin.New()
			router.POST("/sync", authMiddleware.Validate(context.Background()),
				FileProcessSyncHandler(context.Background(), &grpc.ClientConn{}, client, nil, []byte(gatewayCapabilityKey)))
			request := httptest.NewRequest(http.MethodPost, "/sync", bytes.NewBufferString(
				`{"id":"550e8400-e29b-41d4-a716-446655440000","type":"image_resize","source_key":"users/user-a/source.png","dest_key":"users/user-a/dest.png"}`,
			))
			request.Header.Set("Content-Type", "application/json")
			request.Header.Set(pb.ProcessingCapabilityHeader, capability)
			if testCase.cookie != "" || testCase.name == "empty cookie falls back" {
				request.AddCookie(&http.Cookie{Name: middleware.AccessTokenCookieName, Value: testCase.cookie, HttpOnly: true, Secure: true})
			}
			if testCase.header != "" {
				request.Header.Set("Authorization", testCase.header)
			}
			recorder := httptest.NewRecorder()
			router.ServeHTTP(recorder, request)
			require.Equal(t, testCase.status, recorder.Code)
			if testCase.status != http.StatusOK {
				require.False(t, client.called)
				return
			}
			require.True(t, client.called)
			outgoing, ok := metadata.FromOutgoingContext(client.ctx)
			require.True(t, ok)
			require.Equal(t, []string{"Bearer " + tokenA}, outgoing.Get("authorization"))
			require.Equal(t, []string{capability}, outgoing.Get(strings.ToLower(pb.ProcessingCapabilityHeader)))
			require.Empty(t, outgoing.Get("cookie"), "unrelated browser cookies must not enter gRPC")
			require.NotContains(t, recorder.Body.String(), tokenA)
			require.NotContains(t, recorder.Body.String(), capability)
		})
	}
}
