package main

import (
	"context"
	"crypto/rsa"
	"errors"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/file-processor/internal/config"
)

type revocationCheckerStub struct {
	revoked bool
	err     error
	seenJTI string
}

func (s *revocationCheckerStub) IsRevoked(_ context.Context, jti string) (bool, error) {
	s.seenJTI = jti
	return s.revoked, s.err
}

func strictAuthClaims(now time.Time) jwt.MapClaims {
	return jwt.MapClaims{
		"sub":       "user-strict",
		"jti":       "session-strict",
		"aud":       defaultJWTAudience,
		"iss":       "https://issuer.example",
		"iat":       now.Add(-time.Minute).Unix(),
		"exp":       now.Add(time.Hour).Unix(),
		"is_active": true,
	}
}

func strictAuthOptions(now time.Time, checker revocationChecker) jwtAuthOptions {
	return jwtAuthOptions{
		Audience:          defaultJWTAudience,
		Issuer:            "https://issuer.example",
		RequireIssuer:     true,
		Revocations:       checker,
		RequireRevocation: checker != nil,
		RequireRS256:      true,
		Now:               func() time.Time { return now },
	}
}

func strictRS256Token(t *testing.T, key *rsa.PrivateKey, now time.Time, mutate func(jwt.MapClaims)) string {
	t.Helper()
	claims := strictAuthClaims(now)
	if mutate != nil {
		mutate(claims)
	}
	return signedToken(t, jwt.SigningMethodRS256, key, claims)
}

func TestParseAndValidateJWT_StrictRS256Contract(t *testing.T) {
	now := time.Date(2026, 9, 14, 12, 0, 0, 0, time.UTC)
	key := generateRSAKey(t)
	checker := &revocationCheckerStub{}
	token := strictRS256Token(t, key, now, nil)

	claims, err := parseAndValidateJWT(context.Background(), token, "", &key.PublicKey, strictAuthOptions(now, checker))
	require.NoError(t, err)
	assert.Equal(t, "user-strict", claims["sub"])
	assert.Equal(t, "session-strict", checker.seenJTI)
}

func TestParseAndValidateJWT_RejectsStrictClaimAndAlgorithmViolations(t *testing.T) {
	now := time.Date(2026, 9, 14, 12, 0, 0, 0, time.UTC)
	key := generateRSAKey(t)
	cases := []struct {
		name   string
		mutate func(jwt.MapClaims)
		want   error
	}{
		{name: "missing issuer", mutate: func(c jwt.MapClaims) { delete(c, "iss") }},
		{name: "wrong issuer", mutate: func(c jwt.MapClaims) { c["iss"] = "https://other.example" }},
		{name: "missing exp", mutate: func(c jwt.MapClaims) { delete(c, "exp") }},
		{name: "missing iat", mutate: func(c jwt.MapClaims) { delete(c, "iat") }},
		{name: "missing jti", mutate: func(c jwt.MapClaims) { delete(c, "jti") }},
		{name: "missing active claim", mutate: func(c jwt.MapClaims) { delete(c, "is_active") }},
		{name: "invalid tenant type", mutate: func(c jwt.MapClaims) { c["tenant_id"] = 42 }},
		{name: "inactive", mutate: func(c jwt.MapClaims) { c["is_active"] = false }, want: errInactiveToken},
		{name: "iat too old", mutate: func(c jwt.MapClaims) { c["iat"] = now.Add(-jwtMaxTokenAge - time.Minute).Unix() }},
		{name: "iat too far future", mutate: func(c jwt.MapClaims) { c["iat"] = now.Add(jwtClockSkew + time.Minute).Unix() }},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			_, err := parseAndValidateJWT(context.Background(), strictRS256Token(t, key, now, tc.mutate), "", &key.PublicKey, strictAuthOptions(now, nil))
			require.Error(t, err)
			if tc.want != nil {
				assert.ErrorIs(t, err, tc.want)
			}
		})
	}

	hs := signedToken(t, jwt.SigningMethodHS256, []byte("hmac-secret"), strictAuthClaims(now))
	_, err := parseAndValidateJWT(context.Background(), hs, "hmac-secret", &key.PublicKey, strictAuthOptions(now, nil))
	assert.Error(t, err)

	rs384 := signedToken(t, jwt.SigningMethodRS384, key, strictAuthClaims(now))
	_, err = parseAndValidateJWT(context.Background(), rs384, "", &key.PublicKey, strictAuthOptions(now, nil))
	assert.Error(t, err)
}

func TestParseAndValidateJWT_RevocationFailsClosed(t *testing.T) {
	now := time.Date(2026, 9, 14, 12, 0, 0, 0, time.UTC)
	key := generateRSAKey(t)
	token := strictRS256Token(t, key, now, nil)

	revoked := &revocationCheckerStub{revoked: true}
	_, err := parseAndValidateJWT(context.Background(), token, "", &key.PublicKey, strictAuthOptions(now, revoked))
	assert.ErrorIs(t, err, errSessionRevoked)

	failed := &revocationCheckerStub{err: errors.New("redis unavailable")}
	_, err = parseAndValidateJWT(context.Background(), token, "", &key.PublicKey, strictAuthOptions(now, failed))
	assert.ErrorIs(t, err, errRevocationStoreUnavailable)

	missing := strictAuthOptions(now, nil)
	missing.RequireRevocation = true
	_, err = parseAndValidateJWT(context.Background(), token, "", &key.PublicKey, missing)
	assert.ErrorIs(t, err, errRevocationStoreUnavailable)
}

func TestStrictJWTOptions_ReleaseRequiresTrustConfiguration(t *testing.T) {
	base := &config.Config{Environment: "production", JWTAudience: defaultJWTAudience}
	_, err := strictJWTOptions(base, nil, nil)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "FP_JWT_ISSUER")

	base.JWTIssuer = "https://issuer.example"
	key := generateRSAKey(t)
	_, err = strictJWTOptions(base, &key.PublicKey, nil)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "revocation Redis")

	checker := &revocationCheckerStub{}
	base.RevocationRedisURL = "redis://localhost:6379/0"
	opts, err := strictJWTOptions(base, &key.PublicKey, checker)
	require.NoError(t, err)
	assert.True(t, opts.RequireRS256)
	assert.True(t, opts.RequireIssuer)
	assert.True(t, opts.RequireRevocation)
}

func TestRedisCapabilityReplayGuard_NilAndInvalidInputsFailClosed(t *testing.T) {
	guard := (*redisCapabilityReplayGuard)(nil)
	accepted, err := guard.Consume(context.Background(), "nonce", time.Now().Add(time.Minute))
	assert.False(t, accepted)
	assert.Error(t, err)

	guard = &redisCapabilityReplayGuard{}
	accepted, err = guard.Consume(context.Background(), "nonce", time.Now().Add(time.Minute))
	assert.False(t, accepted)
	assert.Error(t, err)
}

func TestReplaySetAdmissionResultTreatsNXMissAsReplay(t *testing.T) {
	accepted, err := replaySetAdmissionResult("", redis.Nil)
	assert.NoError(t, err)
	assert.False(t, accepted)

	accepted, err = replaySetAdmissionResult("", errors.New("redis unavailable"))
	assert.Error(t, err)
	assert.False(t, accepted)

	accepted, err = replaySetAdmissionResult("OK", nil)
	assert.NoError(t, err)
	assert.True(t, accepted)
	accepted, err = replaySetAdmissionResult("", nil)
	assert.NoError(t, err)
	assert.False(t, accepted)
}
