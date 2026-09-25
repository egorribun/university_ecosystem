package main

import (
	"context"
	"crypto/rsa"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/require"
	pb "github.com/university-ecosystem/core/gen/go/file_processor/v1"
	"github.com/university-ecosystem/file-processor/internal/config"
	"go.temporal.io/sdk/client"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

type coverageReplayErrorGuard struct{}

func (coverageReplayErrorGuard) Consume(context.Context, string, time.Time) (bool, error) {
	return false, errors.New("synthetic replay registry failure")
}

func TestStrictJWTOptionsAndParserUseConfiguredClockAndKeySetBranch(t *testing.T) {
	opts, err := strictJWTOptionsWithKeySet(&config.Config{}, nil, nil, nil)
	require.NoError(t, err)
	require.NotNil(t, opts.Now)
	require.WithinDuration(t, time.Now().UTC(), opts.Now(), time.Second)

	originalParse := parseJWTFunc
	t.Cleanup(func() { parseJWTFunc = originalParse })
	parseJWTFunc = func(string, jwt.Keyfunc, ...jwt.ParserOption) (*jwt.Token, error) {
		return nil, nil
	}
	_, err = parseJWTClaims("synthetic", "secret", nil, jwtAuthOptions{RequireKID: true})
	require.ErrorIs(t, err, errInvalidJWTClaims)
}

func TestFetchJWKSKeySetRejectsNilResponseAndBody(t *testing.T) {
	originalDo := doJWKSRequestFunc
	t.Cleanup(func() { doJWKSRequestFunc = originalDo })
	doJWKSRequestFunc = func(*http.Client, *http.Request) (*http.Response, error) {
		return nil, nil
	}
	_, err := fetchJWKSKeySet(context.Background(), http.DefaultClient, "http://backend/jwks")
	require.ErrorContains(t, err, "returned no response")

	doJWKSRequestFunc = func(*http.Client, *http.Request) (*http.Response, error) {
		return &http.Response{StatusCode: http.StatusOK, Body: nil}, nil
	}
	_, err = fetchJWKSKeySet(context.Background(), http.DefaultClient, "http://backend/jwks")
	require.ErrorContains(t, err, "empty response body")
}

func TestRunMainFailsClosedWhenJWKSInitializationFails(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
		_, _ = io.WriteString(writer, "malformed")
	}))
	server.Close()
	// A closed local endpoint is valid configuration and makes the initial
	// trust-root fetch fail before any external service is initialized.
	t.Setenv("FP_ENVIRONMENT", "development")
	t.Setenv("FP_JWT_SECRET", "run-main-jwks-test-secret")
	t.Setenv("FP_JWKS_URL", server.URL)
	t.Setenv("FP_RSA_PUBLIC_KEY_PEM", "")
	t.Setenv("FP_RSA_PUBLIC_KEY_FILE", "")

	err := runMain(context.Background())
	require.ErrorContains(t, err, "initial JWKS fetch failed")
}

func TestRunMainUsesSharedRedisReplayAuthority(t *testing.T) {
	server := newCoverageRedisServer(t, "active")
	configureRunMainStubs(t)
	t.Setenv("FP_REVOCATION_REDIS_URL", "redis://"+server.addr()+"/0")
	setupGRPCServerFunc = func(context.Context, *config.Config, *rsa.PublicKey, client.Client, ...any) (*grpc.Server, error) {
		return grpc.NewServer(), nil
	}
	setupGraphQLServerFunc = func(context.Context, *config.Config, *rsa.PublicKey, client.Client, ...any) (*http.Server, error) {
		return &http.Server{}, nil
	}
	runServersFunc = func(context.Context, *grpc.Server, *http.Server, *config.Config, *slog.Logger) error {
		return nil
	}

	err := runMain(context.Background())
	require.NoError(t, err)
}

func TestRunMainPropagatesRevocationRedisInitializationFailure(t *testing.T) {
	t.Setenv("FP_ENVIRONMENT", "development")
	t.Setenv("FP_JWT_SECRET", "run-main-redis-test-secret")
	t.Setenv("FP_REVOCATION_REDIS_URL", "not-a-redis-url")
	err := runMain(context.Background())
	require.ErrorContains(t, err, "parse revocation Redis URL")
}

func TestRunMainRejectsReleaseJWTWithoutRSAKey(t *testing.T) {
	redisServer := newCoverageRedisServer(t, "active")
	t.Setenv("FP_ENVIRONMENT", "staging")
	t.Setenv("FP_JWT_SECRET", "run-main-release-test-secret")
	t.Setenv("FP_PROCESSING_CAPABILITY_SECRET", strings.Join([]string{"pA7!", "qB8@", "rC9#", "sD0$", "tE1%", "uF2^", "vG3&", "wH4*"}, ""))
	t.Setenv("FP_MINIO_SECURE", "true")
	t.Setenv("FP_TEMPORAL_TLS_DISABLED", "false")
	t.Setenv("FP_OTLP_INSECURE", "false")
	t.Setenv("FP_SPIFFE_ENABLED", "true")
	t.Setenv("FP_RSA_PUBLIC_KEY_PEM", "")
	t.Setenv("FP_RSA_PUBLIC_KEY_FILE", "")
	t.Setenv("FP_JWKS_URL", "")
	t.Setenv("FP_REVOCATION_REDIS_URL", "redis://"+redisServer.addr()+"/0")

	err := runMain(context.Background())
	require.ErrorContains(t, err, "RSA public key is required")
}

func TestHandleFileProcessDeliveryRecordsReplayAdmissionFailure(t *testing.T) {
	job := natsCapabilityJob()
	payload := natsCapabilityPayload(t, job, []byte(natsCapabilityKey), time.Now().UTC())
	msg := &fakeProcessDeliveryMessage{payload: payload}
	stub := &natsTemporalClientStub{calls: make(chan struct{}, 1)}
	handleFileProcessDelivery(context.Background(), msg, stub, discardLogger(), []byte(natsCapabilityKey), coverageReplayErrorGuard{})
	require.Equal(t, 1, msg.ackCount)
	require.Zero(t, msg.termCount)
	require.Zero(t, msg.nakCount)
}

func TestCloseRevocationRedisLogsCloseFailure(t *testing.T) {
	original := closeRevocationRedisClientFunc
	t.Cleanup(func() { closeRevocationRedisClientFunc = original })
	closeRevocationRedisClientFunc = func(*redis.Client) error { return errors.New("synthetic close failure") }
	closeRevocationRedis(context.Background(), discardLogger(), redis.NewClient(&redis.Options{Addr: "127.0.0.1:1"}))
}

func TestGRPCAuthorizationOptionBranches(t *testing.T) {
	replayGuard := pb.NewCapabilityReplayRegistry(1)
	logger, _, provided, parsedReplay := parseGRPCServerOptions(jwtAuthOptions{Audience: "audience"}, replayGuard)
	require.NotNil(t, logger)
	require.NotNil(t, provided)
	require.Same(t, replayGuard, parsedReplay)

	_, err := resolveGRPCAuthOptions(&config.Config{}, nil, &jwtAuthOptions{RequireRS256: true})
	require.ErrorContains(t, err, "RSA public key")
	resolved, err := resolveGRPCAuthOptions(&config.Config{}, nil, &jwtAuthOptions{Audience: "audience"})
	require.NoError(t, err)
	require.Equal(t, "audience", resolved.Audience)

	_, err = setupGRPCServer(context.Background(), &config.Config{Environment: "staging"}, nil, nil, discardLogger())
	require.ErrorContains(t, err, "JWT_ISSUER")
}

func TestGraphQLAuthorizationOptionBranches(t *testing.T) {
	_, err := setupGraphQLServer(
		context.Background(),
		&config.Config{},
		nil,
		nil,
		discardLogger(),
		jwtAuthOptions{RequireRS256: true},
		pb.NewCapabilityReplayRegistry(1),
	)
	require.ErrorContains(t, err, "RSA public key")
}

func TestJWTKeyFuncRejectsAlgorithmVariants(t *testing.T) {
	rsaKey := generateRSAKey(t)
	_, err := jwtKeyFunc("", &rsaKey.PublicKey)(jwt.New(jwt.SigningMethodRS512))
	require.ErrorContains(t, err, "unexpected RSA signing method")
	_, err = jwtKeyFunc("hmac-secret", nil)(jwt.New(jwt.SigningMethodHS384))
	require.ErrorContains(t, err, "unexpected HMAC signing method")
}

func TestHTTPMiddlewareMapsRevocationAndInactiveStatuses(t *testing.T) {
	now := time.Now().UTC()
	token := signedToken(t, jwt.SigningMethodHS256, []byte("hmac-secret"), validAuthClaims("http-user", "http-session"))
	revocationOptions := jwtAuthOptions{
		Audience:          defaultJWTAudience,
		RequireRevocation: true,
		Revocations:       &revocationCheckerStub{err: errors.New("redis unavailable")},
		Now:               func() time.Time { return now },
	}
	recorder := httptest.NewRecorder()
	request := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/graphql", nil)
	request.Header.Set("Authorization", "Bearer "+token)
	httpJWTMiddlewareWithOptions("hmac-secret", nil, nil, revocationOptions, http.HandlerFunc(func(http.ResponseWriter, *http.Request) {})).ServeHTTP(recorder, request)
	require.Equal(t, http.StatusServiceUnavailable, recorder.Code)

	inactiveClaims := validAuthClaims("inactive-user", "inactive-session")
	inactiveClaims["is_active"] = false
	inactiveToken := signedToken(t, jwt.SigningMethodHS256, []byte("hmac-secret"), inactiveClaims)
	recorder = httptest.NewRecorder()
	request = httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/graphql", nil)
	request.Header.Set("Authorization", "Bearer "+inactiveToken)
	httpJWTMiddlewareWithOptions("hmac-secret", nil, discardLogger(), jwtAuthOptions{Audience: defaultJWTAudience, Now: func() time.Time { return now }}, http.HandlerFunc(func(http.ResponseWriter, *http.Request) {})).ServeHTTP(recorder, request)
	require.Equal(t, http.StatusForbidden, recorder.Code)
}

func TestGRPCAuthMapsRevocationAndInactiveStatuses(t *testing.T) {
	now := time.Now().UTC()
	revocationToken := signedToken(t, jwt.SigningMethodHS256, []byte("hmac-secret"), validAuthClaims("grpc-user", "grpc-session"))
	revocationFn := authFuncWithOptions("hmac-secret", nil, nil, jwtAuthOptions{
		Audience:          defaultJWTAudience,
		RequireRevocation: true,
		Revocations:       &revocationCheckerStub{err: errors.New("redis unavailable")},
		Now:               func() time.Time { return now },
	})
	_, err := revocationFn(metadataCtx(revocationToken))
	require.Equal(t, codes.Unavailable, status.Code(err))

	inactiveClaims := validAuthClaims("grpc-inactive", "grpc-inactive-session")
	inactiveClaims["is_active"] = false
	inactiveToken := signedToken(t, jwt.SigningMethodHS256, []byte("hmac-secret"), inactiveClaims)
	inactiveFn := authFuncWithOptions("hmac-secret", nil, discardLogger(), jwtAuthOptions{Audience: defaultJWTAudience, Now: func() time.Time { return now }})
	_, err = inactiveFn(metadataCtx(inactiveToken))
	require.Equal(t, codes.PermissionDenied, status.Code(err))
}
