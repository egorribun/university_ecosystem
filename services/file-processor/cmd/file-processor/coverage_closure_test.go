package main

import (
	"bufio"
	"context"
	"crypto/rsa"
	"errors"
	"io"
	"log/slog"
	"net"
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/file-processor/internal/config"
)

// coverageRedisServer is a deliberately small RESP server used to exercise the
// concrete go-redis integrations without requiring a developer daemon or a
// Docker service. It implements only the commands used by the revocation and
// replay guards and never stores secrets from the test request.
type coverageRedisServer struct {
	listener net.Listener
	mode     string
	wg       sync.WaitGroup
}

func newCoverageRedisServer(t *testing.T, mode string) *coverageRedisServer {
	t.Helper()
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	require.NoError(t, err)
	server := &coverageRedisServer{listener: listener, mode: mode}
	server.wg.Add(1)
	go server.accept()
	t.Cleanup(func() {
		_ = listener.Close()
		server.wg.Wait()
	})
	return server
}

func (s *coverageRedisServer) accept() {
	defer s.wg.Done()
	for {
		conn, err := s.listener.Accept()
		if err != nil {
			return
		}
		s.wg.Add(1)
		go func() {
			defer s.wg.Done()
			defer conn.Close()
			s.serve(conn)
		}()
	}
}

func (s *coverageRedisServer) serve(conn net.Conn) {
	reader := bufio.NewReader(conn)
	for {
		line, err := reader.ReadString('\n')
		if err != nil {
			return
		}
		if len(line) < 3 || line[0] != '*' {
			return
		}
		count, err := strconv.Atoi(strings.TrimSpace(line[1:]))
		if err != nil || count < 1 {
			return
		}
		args := make([]string, count)
		for index := range args {
			lengthLine, readErr := reader.ReadString('\n')
			if readErr != nil || len(lengthLine) < 3 || lengthLine[0] != '$' {
				return
			}
			length, parseErr := strconv.Atoi(strings.TrimSpace(lengthLine[1:]))
			if parseErr != nil || length < 0 {
				return
			}
			value := make([]byte, length+2)
			if _, readErr = io.ReadFull(reader, value); readErr != nil {
				return
			}
			args[index] = string(value[:length])
		}

		command := strings.ToUpper(args[0])
		response := "+OK\r\n"
		switch command {
		case "PING":
			response = "+PONG\r\n"
		case "EXISTS":
			if s.mode == "revoked" {
				response = ":1\r\n"
			} else {
				response = ":0\r\n"
			}
		case "SET":
			switch s.mode {
			case "replay":
				response = "+OK\r\n"
			case "replay-miss":
				response = "$-1\r\n"
			case "error":
				response = "-ERR synthetic redis failure\r\n"
			}
		default:
			response = "-ERR unsupported command\r\n"
		}
		if _, err = io.WriteString(conn, response); err != nil {
			return
		}
	}
}

func (s *coverageRedisServer) addr() string { return s.listener.Addr().String() }

func newCoverageRedisClient(t *testing.T, server *coverageRedisServer) *redis.Client {
	t.Helper()
	client := redis.NewClient(&redis.Options{
		Addr:         server.addr(),
		MaxRetries:   0,
		DialTimeout:  250 * time.Millisecond,
		ReadTimeout:  250 * time.Millisecond,
		WriteTimeout: 250 * time.Millisecond,
	})
	t.Cleanup(func() { _ = client.Close() })
	return client
}

func TestRedisRevocationCheckerCoversHealthyAndFailClosedPaths(t *testing.T) {
	var nilChecker *redisRevocationChecker
	_, err := nilChecker.IsRevoked(context.Background(), "session")
	require.ErrorIs(t, err, errRevocationStoreUnavailable)
	_, err = (&redisRevocationChecker{}).IsRevoked(context.Background(), "session")
	require.ErrorIs(t, err, errRevocationStoreUnavailable)
	client := newCoverageRedisClient(t, newCoverageRedisServer(t, "active"))
	checker := &redisRevocationChecker{client: client}
	_, err = checker.IsRevoked(context.Background(), "")
	require.ErrorIs(t, err, errRevocationStoreUnavailable)
	revoked, err := checker.IsRevoked(context.Background(), "session-healthy")
	require.NoError(t, err)
	require.False(t, revoked)

	revokedClient := newCoverageRedisClient(t, newCoverageRedisServer(t, "revoked"))
	revoked, err = (&redisRevocationChecker{client: revokedClient}).IsRevoked(context.Background(), "session-revoked")
	require.NoError(t, err)
	require.True(t, revoked)

	failedClient := redis.NewClient(&redis.Options{Addr: "127.0.0.1:1", MaxRetries: 0, DialTimeout: 50 * time.Millisecond, ReadTimeout: 50 * time.Millisecond})
	t.Cleanup(func() { _ = failedClient.Close() })
	_, err = (&redisRevocationChecker{client: failedClient}).IsRevoked(context.Background(), "session-failed")
	require.ErrorContains(t, err, "check revoked session")
}

func TestRedisCapabilityReplayGuardCoversAdmissionOutcomes(t *testing.T) {
	var nilGuard *redisCapabilityReplayGuard
	accepted, err := nilGuard.Consume(context.Background(), "nonce", time.Now().Add(time.Minute))
	require.False(t, accepted)
	require.Error(t, err)
	accepted, err = (&redisCapabilityReplayGuard{}).Consume(context.Background(), "nonce", time.Now().Add(time.Minute))
	require.False(t, accepted)
	require.Error(t, err)
	accepted, err = (&redisCapabilityReplayGuard{client: newCoverageRedisClient(t, newCoverageRedisServer(t, "replay"))}).Consume(context.Background(), "nonce-healthy", time.Now().Add(time.Minute))
	require.True(t, accepted)
	require.NoError(t, err)
	accepted, err = (&redisCapabilityReplayGuard{client: newCoverageRedisClient(t, newCoverageRedisServer(t, "replay-miss"))}).Consume(context.Background(), "nonce-replayed", time.Now().Add(time.Minute))
	require.False(t, accepted)
	require.NoError(t, err)
	accepted, err = (&redisCapabilityReplayGuard{client: newCoverageRedisClient(t, newCoverageRedisServer(t, "error"))}).Consume(context.Background(), "nonce-error", time.Now().Add(time.Minute))
	require.False(t, accepted)
	require.ErrorContains(t, err, "consume processing capability replay admission")
	failedClient := redis.NewClient(&redis.Options{Addr: "127.0.0.1:1", MaxRetries: 0, DialTimeout: 50 * time.Millisecond, ReadTimeout: 50 * time.Millisecond})
	t.Cleanup(func() { _ = failedClient.Close() })
	accepted, err = (&redisCapabilityReplayGuard{client: failedClient}).Consume(context.Background(), "nonce-unavailable", time.Now().Add(time.Minute))
	require.False(t, accepted)
	require.Error(t, err)
	originalNow := redisCapabilityNowFunc
	originalTTL := redisCapabilityTTLFunc
	t.Cleanup(func() {
		redisCapabilityNowFunc = originalNow
		redisCapabilityTTLFunc = originalTTL
	})
	base := time.Date(2026, 9, 14, 12, 0, 0, 0, time.UTC)
	redisCapabilityNowFunc = func() time.Time { return base }
	redisCapabilityTTLFunc = func(time.Time) time.Duration { return -time.Second }
	replayClient := newCoverageRedisClient(t, newCoverageRedisServer(t, "replay"))
	_, err = (&redisCapabilityReplayGuard{client: replayClient}).Consume(context.Background(), "nonce-race", base.Add(time.Second))
	require.ErrorContains(t, err, "admission is expired")
}

func TestNewRevocationRedisClientCoversParsePingAndSuccess(t *testing.T) {
	client, err := newRevocationRedisClient(context.Background(), "not-a-redis-url")
	require.Nil(t, client)
	require.ErrorContains(t, err, "parse revocation Redis URL")

	client, err = newRevocationRedisClient(context.Background(), "redis://127.0.0.1:1/0")
	require.Nil(t, client)
	require.ErrorContains(t, err, "connect to revocation Redis")
	originalClose := closeRevocationRedisClientFunc
	t.Cleanup(func() { closeRevocationRedisClientFunc = originalClose })
	closeRevocationRedisClientFunc = func(*redis.Client) error { return errors.New("synthetic close failure") }
	client, err = newRevocationRedisClient(context.Background(), "redis://127.0.0.1:1/0")
	require.Nil(t, client)
	require.ErrorContains(t, err, "close client")

	server := newCoverageRedisServer(t, "active")
	client, err = newRevocationRedisClient(context.Background(), "redis://"+server.addr()+"/0")
	require.NoError(t, err)
	require.NotNil(t, client)
	require.NoError(t, client.Close())
}

func TestStrictJWTOptionsAndParserFailClosedBranches(t *testing.T) {
	_, err := strictJWTOptionsWithKeySet(nil, nil, nil, nil)
	require.ErrorContains(t, err, "configuration is nil")
	_, err = strictJWTOptionsWithKeySet(&config.Config{Environment: "development"}, nil, nil, nil)
	require.NoError(t, err)
	require.ErrorContains(t, validateJWTAuthOptionsWithKeySet(jwtAuthOptions{RequireRS256: true}, nil), "RSA public key")

	_, err = parseAndValidateJWT(context.Background(), "unused", "secret", nil, jwtAuthOptions{RequireIssuer: true, Issuer: ""})
	require.ErrorIs(t, err, errInvalidJWTClaims)

	original := parseJWTFunc
	t.Cleanup(func() { parseJWTFunc = original })
	parseJWTFunc = func(string, jwt.Keyfunc, ...jwt.ParserOption) (*jwt.Token, error) {
		return nil, nil
	}
	_, err = parseJWTClaims("synthetic", "secret", nil, jwtAuthOptions{})
	require.ErrorIs(t, err, errInvalidJWTClaims)
	parseJWTFunc = func(string, jwt.Keyfunc, ...jwt.ParserOption) (*jwt.Token, error) {
		return &jwt.Token{Valid: true, Claims: jwt.RegisteredClaims{}}, nil
	}
	_, err = parseJWTClaims("synthetic", "secret", nil, jwtAuthOptions{})
	require.ErrorIs(t, err, errInvalidJWTClaims)
}

func TestStrictJWTOptionsDefaultNowAndKeySetParser(t *testing.T) {
	options, err := strictJWTOptionsWithKeySet(&config.Config{}, nil, nil, nil)
	require.NoError(t, err)
	require.NotNil(t, options.Now)
	require.False(t, options.Now().IsZero())

	now := time.Date(2026, 9, 14, 12, 0, 0, 0, time.UTC)
	key := generateRSAKey(t)
	store := newRSAKeySetStore()
	store.Store(rsaKeySet{"primary": &key.PublicKey})
	token := jwt.NewWithClaims(jwt.SigningMethodRS256, strictAuthClaims(now))
	token.Header["kid"] = "primary"
	tokenString, err := token.SignedString(key)
	require.NoError(t, err)
	claims, err := parseJWTClaims(tokenString, "", nil, jwtAuthOptions{
		Audience:     defaultJWTAudience,
		RequireRS256: true,
		KeySet:       store,
		RequireKID:   true,
		ActiveKID:    "primary",
		Now:          func() time.Time { return now },
	})
	require.NoError(t, err)
	require.Equal(t, "user-strict", claims["sub"])
}

func TestValidateJWTClaimsRejectsMalformedApplicationClaims(t *testing.T) {
	now := time.Date(2026, 9, 14, 12, 0, 0, 0, time.UTC)
	cases := []struct {
		name   string
		mutate func(jwt.MapClaims)
	}{
		{name: "sub type", mutate: func(c jwt.MapClaims) { c["sub"] = 42 }},
		{name: "sub empty", mutate: func(c jwt.MapClaims) { c["sub"] = "" }},
		{name: "jti type", mutate: func(c jwt.MapClaims) { c["jti"] = 42 }},
		{name: "jti empty", mutate: func(c jwt.MapClaims) { c["jti"] = "" }},
		{name: "active type", mutate: func(c jwt.MapClaims) { c["is_active"] = "true" }},
		{name: "tenant type", mutate: func(c jwt.MapClaims) { c["tenant_id"] = 42 }},
		{name: "tenant empty is invalid", mutate: func(c jwt.MapClaims) { c["tenant_id"] = "" }},
		{name: "iat type", mutate: func(c jwt.MapClaims) { c["iat"] = "not-a-number" }},
		{name: "iat nil", mutate: func(c jwt.MapClaims) { c["iat"] = nil }},
		{name: "iat too old", mutate: func(c jwt.MapClaims) { c["iat"] = now.Add(-jwtMaxTokenAge - time.Minute).Unix() }},
		{name: "iat too new", mutate: func(c jwt.MapClaims) { c["iat"] = now.Add(jwtClockSkew + time.Minute).Unix() }},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			claims := strictAuthClaims(now)
			tc.mutate(claims)
			require.Error(t, validateJWTClaims(claims, now))
		})
	}
}

func nilCoverageContext() context.Context { return nil }

type coverageCloseErrorBody struct{ io.Reader }

func (coverageCloseErrorBody) Close() error { return errors.New("synthetic close failure") }

func TestJWKSUncoveredBoundaryBranches(t *testing.T) {
	key := generateRSAKey(t)
	_, err := initializeJWKSKeySet(nilCoverageContext(), &config.Config{}, nil, nil)
	require.ErrorContains(t, err, "context is nil")
	static, err := initializeJWKSKeySet(context.Background(), &config.Config{JWTActiveKID: "primary"}, &key.PublicKey, nil)
	require.NoError(t, err)
	require.NotNil(t, static)

	startJWKSRefresher(nilCoverageContext(), "http://backend/jwks", time.Second, static, nil)
	canceled, cancel := context.WithCancel(context.Background())
	cancel()
	startJWKSRefresher(canceled, "http://backend/jwks", time.Millisecond, static, nil)
	startJWKSRefresher(context.Background(), "", time.Second, static, nil)
	startJWKSRefresher(context.Background(), "http://backend/jwks", time.Second, nil, nil)
	require.ErrorContains(t, refreshJWKSOnce(context.Background(), http.DefaultClient, "http://backend/jwks", nil), "store is nil")

	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
		_, _ = writer.Write(marshalJWKS(t, rsaJWK("only", &key.PublicKey)))
	}))
	t.Cleanup(server.Close)
	keys, err := fetchJWKSKeySet(context.Background(), nil, server.URL)
	require.NoError(t, err)
	require.Len(t, keys, 1)
	_, err = fetchJWKSKeySet(nilCoverageContext(), http.DefaultClient, server.URL)
	require.ErrorContains(t, err, "context is nil")
	_, err = fetchJWKSKeySet(context.Background(), http.DefaultClient, "http://backend/\x00")
	require.Error(t, err)
	originalRequest := newJWKSRequestFunc
	t.Cleanup(func() { newJWKSRequestFunc = originalRequest })
	newJWKSRequestFunc = func(context.Context, string, string, io.Reader) (*http.Request, error) {
		return nil, errors.New("synthetic request creation failure")
	}
	_, err = fetchJWKSKeySet(context.Background(), http.DefaultClient, "http://backend/jwks")
	require.ErrorContains(t, err, "request creation failed")
	newJWKSRequestFunc = originalRequest

	closeErrorClient := &http.Client{Transport: roundTripFunc(func(*http.Request) (*http.Response, error) {
		body := string(marshalJWKS(t, rsaJWK("close", &key.PublicKey)))
		return &http.Response{StatusCode: http.StatusOK, Body: coverageCloseErrorBody{Reader: strings.NewReader(body)}}, nil
	})}
	_, err = fetchJWKSKeySet(context.Background(), closeErrorClient, "http://backend/jwks")
	require.ErrorContains(t, err, "response close failed")

	_, err = parseJWKSKeySet([]byte(`{"keys":["not-an-object"]}`))
	require.ErrorContains(t, err, "key 0 is invalid")

	resolved, err := resolveJWKSKey("", rsaKeySet{"only": &key.PublicKey}, false)
	require.NoError(t, err)
	require.True(t, resolved.(*rsa.PublicKey).Equal(&key.PublicKey))
	_, err = resolveStaticRSAKey("primary", nil, false, "primary")
	require.ErrorContains(t, err, "no RSA public key")
	_, err = resolveHMACJWTKey(jwt.New(jwt.SigningMethodHS384), "secret", nil, nil, false)
	require.ErrorContains(t, err, "unexpected HMAC signing method")

	asserted := (*rsa.PublicKey)(nil)
	_ = asserted
}

func TestFetchJWKSKeySetAcceptsTransportBoundaryResults(t *testing.T) {
	original := doJWKSRequestFunc
	t.Cleanup(func() { doJWKSRequestFunc = original })

	doJWKSRequestFunc = func(*http.Client, *http.Request) (*http.Response, error) {
		return nil, nil
	}
	_, err := fetchJWKSKeySet(context.Background(), http.DefaultClient, "http://backend/jwks")
	require.ErrorContains(t, err, "no response")

	doJWKSRequestFunc = func(*http.Client, *http.Request) (*http.Response, error) {
		return &http.Response{StatusCode: http.StatusOK}, nil
	}
	_, err = fetchJWKSKeySet(context.Background(), http.DefaultClient, "http://backend/jwks")
	require.ErrorContains(t, err, "empty response body")
}

func TestJWKSStartRefresherWithNilLoggerStopsOnCancel(t *testing.T) {
	store := newRSAKeySetStore()
	ctx, cancel := context.WithCancel(context.Background())
	startJWKSRefresher(ctx, "http://127.0.0.1:1/jwks", time.Millisecond, store, nil)
	cancel()
	time.Sleep(2 * time.Millisecond)
	require.Empty(t, store.Load())
}

func TestJWKSRefresherLogsFailedRefreshAndRetainsSnapshot(t *testing.T) {
	key := generateRSAKey(t)
	store := newRSAKeySetStore()
	store.Store(rsaKeySet{"lkg": &key.PublicKey})
	requestSeen := make(chan struct{})
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
		select {
		case <-requestSeen:
		default:
			close(requestSeen)
		}
		_, _ = io.WriteString(writer, "malformed")
	}))
	t.Cleanup(server.Close)
	ctx, cancel := context.WithCancel(context.Background())
	startJWKSRefresher(ctx, server.URL, time.Millisecond, store, slog.New(slog.NewTextHandler(io.Discard, nil)))
	select {
	case <-requestSeen:
		cancel()
	case <-time.After(3 * time.Second):
		cancel()
		t.Fatal("JWKS refresher did not attempt a refresh")
	}
	require.True(t, store.Load()["lkg"].Equal(&key.PublicKey))
}
