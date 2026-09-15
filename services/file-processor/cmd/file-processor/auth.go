package main

// Authentication for every file-processor ingress lives in this file.  HTTP
// GraphQL and gRPC must not grow subtly different JWT policies: a token that
// reaches one transport is validated by exactly the same algorithm, claim,
// activity and session-revocation contract before any user identity enters a
// request context.

import (
	"context"
	"crypto/rsa"
	"crypto/sha256"
	"errors"
	"fmt"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/golang-jwt/jwt/v5"
	"github.com/redis/go-redis/v9"

	"github.com/university-ecosystem/file-processor/internal/config"
)

const (
	defaultJWTAudience = "university-ecosystem-api"
	jwtClockSkew       = 5 * time.Minute
	jwtMaxTokenAge     = 24 * time.Hour
	redisCheckTimeout  = 50 * time.Millisecond
	capabilityReplayNS = "file-processor:capability-replay:v1:"
)

var (
	errRevocationStoreUnavailable  = errors.New("session revocation store unavailable")
	errSessionRevoked              = errors.New("session revoked")
	errInactiveToken               = errors.New("user account is inactive")
	errInvalidJWTClaims            = errors.New("invalid JWT claims")
	closeRevocationRedisClientFunc = func(client *redis.Client) error { return client.Close() }
	redisCapabilityNowFunc         = func() time.Time { return time.Now().UTC() }
	redisCapabilityTTLFunc         = func(expiresAt time.Time) time.Duration { return time.Until(expiresAt) }
)

type revocationChecker interface {
	IsRevoked(context.Context, string) (bool, error)
}

// redisRevocationChecker reads the same tombstone key written by the Python
// session service and checked by the gateway.  A Redis error is never treated
// as "not revoked"; callers fail closed so a partition cannot turn a revoked
// session into an authenticated file-processing request.
type redisRevocationChecker struct {
	client *redis.Client
}

func (c *redisRevocationChecker) IsRevoked(ctx context.Context, jti string) (bool, error) {
	if c == nil || c.client == nil || !validJWTString(jti, 256) {
		return false, errRevocationStoreUnavailable
	}
	checkCtx, cancel := context.WithTimeout(ctx, redisCheckTimeout)
	defer cancel()
	exists, err := c.client.Exists(checkCtx, "revoked:jti:"+jti).Result()
	if err != nil {
		return false, fmt.Errorf("check revoked session: %w", err)
	}
	return exists > 0, nil
}

// redisCapabilityReplayGuard uses an atomic Redis SET NX with an expiry.  It
// shares the revocation Redis connection, so all file-processor replicas use
// one admission registry in staging/production rather than relying on a
// process-local map.  Only a digest of the nonce is used in the key: bearer
// proofs and their entropy never become Redis key material or observability
// data.
type redisCapabilityReplayGuard struct {
	client *redis.Client
}

func (g *redisCapabilityReplayGuard) Consume(ctx context.Context, nonce string, expiresAt time.Time) (bool, error) {
	now := redisCapabilityNowFunc()
	if g == nil || g.client == nil || !validJWTString(nonce, 128) || !expiresAt.After(now) {
		return false, errors.New("processing capability replay admission is invalid")
	}
	ttl := redisCapabilityTTLFunc(expiresAt)
	if ttl <= 0 {
		return false, errors.New("processing capability replay admission is expired")
	}
	digest := sha256.Sum256([]byte(nonce))
	key := capabilityReplayNS + fmt.Sprintf("%x", digest[:])
	consumeCtx, cancel := context.WithTimeout(ctx, 500*time.Millisecond)
	defer cancel()
	result, err := g.client.SetArgs(consumeCtx, key, "1", redis.SetArgs{Mode: "NX", TTL: ttl}).Result()
	return replaySetAdmissionResult(result, err)
}

func replaySetAdmissionResult(result string, err error) (bool, error) {
	// go-redis represents a successful SET NX miss (the nonce was already
	// admitted) as redis.Nil. That is a normal replay result, not an outage;
	// returning it as an error would make every legitimate duplicate delivery
	// look like a transient infrastructure failure and trigger needless NATS
	// redelivery.
	if errors.Is(err, redis.Nil) {
		return false, nil
	}
	if err != nil {
		return false, fmt.Errorf("consume processing capability replay admission: %w", err)
	}
	return result == "OK", nil
}

func newRevocationRedisClient(ctx context.Context, redisURL string) (*redis.Client, error) {
	options, err := redis.ParseURL(strings.TrimSpace(redisURL))
	if err != nil {
		return nil, fmt.Errorf("parse revocation Redis URL: %w", err)
	}
	client := redis.NewClient(options)
	pingCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	if pingErr := client.Ping(pingCtx).Err(); pingErr != nil {
		if closeErr := closeRevocationRedisClientFunc(client); closeErr != nil {
			return nil, fmt.Errorf("connect to revocation Redis: %w; close client: %v", pingErr, closeErr)
		}
		return nil, fmt.Errorf("connect to revocation Redis: %w", pingErr)
	}
	return client, nil
}

type jwtAuthOptions struct {
	Audience          string
	Issuer            string
	RequireIssuer     bool
	Revocations       revocationChecker
	RequireRevocation bool
	RequireRS256      bool
	// KeySet is an immutable, atomically replaced JWKS snapshot. When present,
	// RS256 verification resolves the token's JOSE kid against this exact set;
	// the verifier never guesses a key from a multi-key snapshot.
	KeySet *rsaKeySetStore
	// ActiveKID identifies the static PEM last-known-good fallback. It is used
	// only when no JWKS snapshot has been accepted yet.
	ActiveKID string
	// RequireKID is enabled for JWKS-backed and release verification. A token
	// without a kid is then rejected even when the set contains one key.
	RequireKID bool
	Now        func() time.Time
}

func (o jwtAuthOptions) normalized() jwtAuthOptions {
	if strings.TrimSpace(o.Audience) == "" {
		o.Audience = defaultJWTAudience
	}
	o.Audience = strings.TrimSpace(o.Audience)
	o.Issuer = strings.TrimSpace(o.Issuer)
	o.ActiveKID = strings.TrimSpace(o.ActiveKID)
	if o.ActiveKID == "" {
		o.ActiveKID = "primary"
	}
	if o.Issuer != "" {
		o.RequireIssuer = true
	}
	if o.Now == nil {
		o.Now = func() time.Time { return time.Now().UTC() }
	}
	return o
}

func strictJWTOptions(cfg *config.Config, rsaPub *rsa.PublicKey, checker revocationChecker) (jwtAuthOptions, error) {
	return strictJWTOptionsWithKeySet(cfg, rsaPub, checker, nil)
}

func strictJWTOptionsWithKeySet(cfg *config.Config, rsaPub *rsa.PublicKey, checker revocationChecker, keySet *rsaKeySetStore) (jwtAuthOptions, error) {
	if cfg == nil {
		return jwtAuthOptions{}, errors.New("file-processor JWT configuration is nil")
	}
	environment := strings.ToLower(strings.TrimSpace(cfg.Environment))
	release := environment == "staging" || environment == "production"
	opts := jwtAuthOptions{
		Audience:          cfg.JWTAudience,
		Issuer:            cfg.JWTIssuer,
		RequireIssuer:     release,
		Revocations:       checker,
		RequireRevocation: release || strings.TrimSpace(cfg.RevocationRedisURL) != "",
		RequireRS256:      release || rsaPub != nil || keySet != nil,
		KeySet:            keySet,
		ActiveKID:         cfg.JWTActiveKID,
		RequireKID:        release || strings.TrimSpace(cfg.JWKSURL) != "",
		Now:               func() time.Time { return time.Now().UTC() },
	}.normalized()
	if err := validateJWTAuthOptionsWithKeySet(opts, rsaPub); err != nil {
		return jwtAuthOptions{}, err
	}
	return opts, nil
}

func validateJWTAuthOptions(opts jwtAuthOptions, rsaPub *rsa.PublicKey) error {
	return validateJWTAuthOptionsWithKeySet(opts, rsaPub)
}

func validateJWTAuthOptionsWithKeySet(opts jwtAuthOptions, rsaPub *rsa.PublicKey) error {
	if opts.RequireIssuer && opts.Issuer == "" {
		return errors.New("FP_JWT_ISSUER is required for staging/production JWT verification")
	}
	if opts.RequireRevocation && opts.Revocations == nil {
		return errors.New("revocation Redis is required for staging/production JWT verification")
	}
	if opts.RequireRS256 && rsaPub == nil && (opts.KeySet == nil || opts.KeySet.Len() == 0) {
		return errors.New("RSA public key is required for staging/production JWT verification")
	}
	return nil
}

func validJWTString(value string, maxLen int) bool {
	return value != "" && len(value) <= maxLen && strings.TrimSpace(value) == value && utf8.ValidString(value) && !strings.ContainsRune(value, '\x00')
}

// parseAndValidateJWT is the sole JWT verifier used by both transport paths.
// It intentionally performs application claim checks after the library's
// signature/time/audience/issuer checks so synthetic or partially-populated
// claims cannot establish an identity context.
func parseAndValidateJWT(ctx context.Context, tokenString, secret string, rsaPub *rsa.PublicKey, options jwtAuthOptions) (jwt.MapClaims, error) {
	options = options.normalized()
	if options.RequireIssuer && options.Issuer == "" {
		return nil, errInvalidJWTClaims
	}
	claims, err := parseJWTClaims(tokenString, secret, rsaPub, options)
	if err != nil {
		return nil, err
	}
	if err := validateJWTClaims(claims, options.Now()); err != nil {
		return nil, err
	}
	if err := validateJWTRevocation(ctx, claims, options); err != nil {
		return nil, err
	}
	return claims, nil
}

func parseJWTClaims(tokenString, secret string, rsaPub *rsa.PublicKey, options jwtAuthOptions) (jwt.MapClaims, error) {
	methods := []string{"HS256"}
	if options.RequireRS256 {
		methods = []string{"RS256"}
	}
	parserOptions := []jwt.ParserOption{
		jwt.WithValidMethods(methods),
		jwt.WithIssuedAt(),
		jwt.WithExpirationRequired(),
		jwt.WithAudience(options.Audience),
		jwt.WithLeeway(jwtClockSkew),
		jwt.WithTimeFunc(options.Now),
	}
	if options.Issuer != "" {
		parserOptions = append(parserOptions, jwt.WithIssuer(options.Issuer))
	}
	keyFunc := jwtKeyFunc(secret, rsaPub)
	if options.KeySet != nil || options.RequireKID {
		keyFunc = jwtKeyFuncWithKeySet(secret, rsaPub, options.KeySet, options.RequireKID, options.ActiveKID, options.RequireRS256)
	}
	token, err := parseJWTFunc(tokenString, keyFunc, parserOptions...)
	if err != nil || token == nil || !token.Valid {
		if err == nil {
			err = errInvalidJWTClaims
		}
		return nil, err
	}
	claims, ok := token.Claims.(jwt.MapClaims)
	if !ok {
		return nil, errInvalidJWTClaims
	}
	return claims, nil
}

func validateJWTClaims(claims jwt.MapClaims, now time.Time) error {
	sub, ok := claims["sub"].(string)
	if !ok || !validJWTString(sub, 256) {
		return fmt.Errorf("%w: missing sub", errInvalidJWTClaims)
	}
	jti, ok := claims["jti"].(string)
	if !ok || !validJWTString(jti, 256) {
		return fmt.Errorf("%w: missing jti", errInvalidJWTClaims)
	}
	active, ok := claims["is_active"].(bool)
	if !ok {
		return fmt.Errorf("%w: missing is_active", errInvalidJWTClaims)
	}
	if !active {
		return errInactiveToken
	}
	if tenant, exists := claims["tenant_id"]; exists {
		if tenantString, tenantOK := tenant.(string); !tenantOK || !validJWTString(tenantString, 256) {
			return fmt.Errorf("%w: invalid tenant_id", errInvalidJWTClaims)
		}
	}
	issuedAt, err := claims.GetIssuedAt()
	if err != nil || issuedAt == nil {
		return fmt.Errorf("%w: invalid iat", errInvalidJWTClaims)
	}
	now = now.UTC()
	if issuedAt.After(now.Add(jwtClockSkew)) || issuedAt.Before(now.Add(-jwtMaxTokenAge)) {
		return fmt.Errorf("%w: iat outside accepted lifetime", errInvalidJWTClaims)
	}
	return nil
}

func validateJWTRevocation(ctx context.Context, claims jwt.MapClaims, options jwtAuthOptions) error {
	if options.RequireRevocation {
		if options.Revocations == nil {
			return errRevocationStoreUnavailable
		}
		jti := claims["jti"].(string)
		revoked, checkErr := options.Revocations.IsRevoked(ctx, jti)
		if checkErr != nil {
			return fmt.Errorf("%w: %v", errRevocationStoreUnavailable, checkErr)
		}
		if revoked {
			return errSessionRevoked
		}
	}
	return nil
}
