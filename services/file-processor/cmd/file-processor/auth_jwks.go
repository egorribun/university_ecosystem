package main

// JWKS verification for the file-processor trust boundary.  The backend is
// the source of truth for public signing keys; this package keeps an immutable
// last-known-good snapshot and replaces it atomically after a bounded fetch.
// No request path performs network I/O or mutates a key map.

import (
	"context"
	"crypto/rsa"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"math/big"
	"net/http"
	"net/url"
	"strings"
	"sync/atomic"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/university-ecosystem/file-processor/internal/config"
)

const (
	maxJWKSBodyBytes          = 64 * 1024
	defaultJWKSRefreshSeconds = 300
	minJWKSRefreshInterval    = time.Second
	maxJWKSRefreshInterval    = 24 * time.Hour
	jwksRequestTimeout        = 5 * time.Second
	maxJWKSKeyIDLength        = 128
	minimumRSAModulusBits     = 2048
	requiredRSAPublicExponent = 65537
)

var (
	newJWKSRequestFunc = http.NewRequestWithContext
	doJWKSRequestFunc  = func(client *http.Client, request *http.Request) (*http.Response, error) {
		return client.Do(request)
	}
)

// rsaKeySet is immutable after it has been published to rsaKeySetStore.  A
// fresh map is created for every Store call so readers never race with a
// refresh and an unsuccessful refresh cannot damage the LKG snapshot.
type rsaKeySet map[string]*rsa.PublicKey

type rsaKeySetStore struct {
	snapshot   atomic.Pointer[rsaKeySet]
	snapshotAt atomic.Int64
	staleAfter time.Duration
}

func newRSAKeySetStore(staleAfter ...time.Duration) *rsaKeySetStore {
	var maxAge time.Duration
	if len(staleAfter) > 0 {
		maxAge = staleAfter[0]
	}
	return &rsaKeySetStore{staleAfter: maxAge}
}

func (s *rsaKeySetStore) Store(keys rsaKeySet) {
	if s == nil || len(keys) == 0 {
		return
	}
	snapshot := make(rsaKeySet, len(keys))
	for kid, key := range keys {
		if err := validateRSAPublicKey(key); err != nil {
			continue
		}
		// PublicKey.N is a mutable big.Int. Clone it before publishing so
		// callers cannot mutate a live snapshot while a request verifies.
		modulus := new(big.Int).Set(key.N)
		snapshot[kid] = &rsa.PublicKey{N: modulus, E: key.E}
	}
	if len(snapshot) == 0 {
		return
	}
	s.snapshot.Store(&snapshot)
	s.snapshotAt.Store(time.Now().UTC().UnixNano())
}

func (s *rsaKeySetStore) Load() rsaKeySet {
	return s.LoadAt(time.Now().UTC())
}

func (s *rsaKeySetStore) LoadAt(now time.Time) rsaKeySet {
	if s == nil {
		return nil
	}
	if s.staleAfter > 0 {
		publishedAt := s.snapshotAt.Load()
		if publishedAt == 0 || !now.UTC().Before(time.Unix(0, publishedAt).Add(s.staleAfter)) {
			return nil
		}
	}
	snapshot := s.snapshot.Load()
	if snapshot == nil {
		return nil
	}
	return *snapshot
}

func (s *rsaKeySetStore) Len() int {
	return len(s.Load())
}

// jwksSnapshotMaxAge bounds how long an outage may keep trusting a retired
// signing key. It is derived from the refresh cadence and the maximum token
// lifetime, with the same clock skew accepted by JWT validation.
func jwksSnapshotMaxAge(refreshInterval time.Duration) time.Duration {
	return boundedJWKSRefreshInterval(refreshInterval) + jwtMaxTokenAge + jwtClockSkew
}

// initializeJWKSKeySet installs the static PEM key as a last-known-good
// fallback, performs one bounded synchronous JWKS fetch when configured, then
// starts a cancellable background refresher.  A configured endpoint with no
// usable static key fails closed if the initial fetch cannot produce a key.
func initializeJWKSKeySet(ctx context.Context, cfg *config.Config, rsaPub *rsa.PublicKey, logger *slog.Logger) (*rsaKeySetStore, error) {
	if cfg == nil {
		return nil, errors.New("file-processor JWKS configuration is nil")
	}
	if ctx == nil {
		return nil, errors.New("file-processor JWKS context is nil")
	}
	// Keep the raw configured value for validation.  Trimming here would turn
	// an invalid deployment value into a different, silently accepted endpoint
	// and would make direct callers of this trust-root initializer disagree with
	// validateConfig.
	endpoint := cfg.JWKSURL
	if endpoint == "" && rsaPub == nil {
		return nil, nil
	}
	if logger == nil {
		logger = slog.Default()
	}
	staleAfter := time.Duration(0)
	if endpoint := cfg.JWKSURL; endpoint != "" {
		staleAfter = jwksSnapshotMaxAge(time.Duration(cfg.JWKSRefreshInterval) * time.Second)
	}
	store := newRSAKeySetStore(staleAfter)
	activeKID := strings.TrimSpace(cfg.JWTActiveKID)
	if activeKID == "" {
		activeKID = "primary"
	}
	if rsaPub != nil {
		store.Store(rsaKeySet{activeKID: rsaPub})
	}
	if endpoint == "" {
		return store, nil
	}
	if err := validateJWKSURL(endpoint); err != nil {
		return nil, err
	}

	client := &http.Client{Timeout: jwksRequestTimeout}
	keys, err := fetchJWKSKeySet(ctx, client, endpoint)
	if err != nil {
		if store.Len() == 0 {
			return nil, fmt.Errorf("initial JWKS fetch failed: %w", err)
		}
		// Static PEM is a deliberate LKG fallback.  Do not include response
		// bodies, key material, or bearer data in this diagnostic.
		logger.WarnContext(ctx, "Initial file-processor JWKS fetch failed; retaining static last-known-good key", "err", err)
	} else {
		store.Store(keys)
	}

	startJWKSRefresher(ctx, endpoint, time.Duration(cfg.JWKSRefreshInterval)*time.Second, store, logger)
	return store, nil
}

// startJWKSRefresher refreshes the complete key set at a bounded interval.
// Failed refreshes leave the prior immutable snapshot untouched (LKG).  The
// context belongs to runMain and therefore terminates the goroutine during a
// graceful process shutdown.
func startJWKSRefresher(ctx context.Context, endpoint string, interval time.Duration, store *rsaKeySetStore, logger *slog.Logger) {
	if ctx == nil || store == nil || strings.TrimSpace(endpoint) == "" {
		return
	}
	if logger == nil {
		logger = slog.Default()
	}
	interval = boundedJWKSRefreshInterval(interval)
	client := &http.Client{Timeout: jwksRequestTimeout}

	go func() {
		ticker := time.NewTicker(interval)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				err := refreshJWKSOnce(ctx, client, endpoint, store)
				if err != nil {
					// Keep the old snapshot on every failure.  Logging only the
					// bounded fetch error prevents accidental secret/PII disclosure.
					logger.WarnContext(ctx, "File-processor JWKS refresh failed; retaining last-known-good keys", "err", err)
					continue
				}
			}
		}
	}()
}

func refreshJWKSOnce(ctx context.Context, client *http.Client, endpoint string, store *rsaKeySetStore) error {
	if store == nil {
		return errors.New("JWKS key-set store is nil")
	}
	keys, err := fetchJWKSKeySet(ctx, client, endpoint)
	if err != nil {
		return err
	}
	store.Store(keys)
	return nil
}

func boundedJWKSRefreshInterval(interval time.Duration) time.Duration {
	if interval <= 0 {
		return defaultJWKSRefreshSeconds * time.Second
	}
	if interval < minJWKSRefreshInterval {
		return minJWKSRefreshInterval
	}
	if interval > maxJWKSRefreshInterval {
		return maxJWKSRefreshInterval
	}
	return interval
}

func validateJWKSURL(endpoint string) error {
	if endpoint == "" || strings.TrimSpace(endpoint) != endpoint || strings.ContainsAny(endpoint, "\r\n") {
		return errors.New("FP_JWKS_URL must be an absolute HTTP(S) URL without credentials, query, or fragment")
	}
	parsed, err := url.Parse(endpoint)
	if err != nil || (parsed.Scheme != "http" && parsed.Scheme != "https") || parsed.Host == "" || parsed.User != nil || parsed.RawQuery != "" || parsed.Fragment != "" {
		return errors.New("FP_JWKS_URL must be an absolute HTTP(S) URL without credentials, query, or fragment")
	}
	return nil
}

func fetchJWKSKeySet(ctx context.Context, client *http.Client, endpoint string) (keys rsaKeySet, err error) {
	if err := validateJWKSURL(endpoint); err != nil {
		return nil, err
	}
	if ctx == nil {
		return nil, errors.New("JWKS fetch context is nil")
	}
	if client == nil {
		client = &http.Client{Timeout: jwksRequestTimeout}
	}
	// JWKS is a trust-root input. Never follow an endpoint-controlled redirect:
	// doing so could turn a reviewed URL into a request to an internal metadata
	// service or another host. Clone the caller's client so this boundary stays
	// fail-closed even when a caller supplies the default redirect policy.
	clientCopy := *client
	clientCopy.CheckRedirect = func(_ *http.Request, _ []*http.Request) error {
		return http.ErrUseLastResponse
	}
	client = &clientCopy
	requestCtx, cancel := context.WithTimeout(ctx, jwksRequestTimeout)
	defer cancel()
	request, err := newJWKSRequestFunc(requestCtx, http.MethodGet, endpoint, nil)
	if err != nil {
		return nil, fmt.Errorf("JWKS request creation failed: %w", err)
	}
	response, err := doJWKSRequestFunc(client, request)
	if err != nil {
		return nil, fmt.Errorf("JWKS fetch failed: %w", err)
	}
	if response == nil {
		return nil, errors.New("JWKS fetch returned no response")
	}
	if response.Body == nil {
		return nil, errors.New("JWKS fetch returned an empty response body")
	}
	defer func() {
		if closeErr := response.Body.Close(); err == nil && closeErr != nil {
			err = fmt.Errorf("JWKS response close failed: %w", closeErr)
		}
	}()
	if response.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("JWKS fetch returned HTTP status %d", response.StatusCode)
	}
	body, err := io.ReadAll(io.LimitReader(response.Body, maxJWKSBodyBytes+1))
	if err != nil {
		return nil, fmt.Errorf("JWKS response read failed: %w", err)
	}
	if len(body) > maxJWKSBodyBytes {
		return nil, fmt.Errorf("JWKS response exceeds %d-byte limit", maxJWKSBodyBytes)
	}
	return parseJWKSKeySet(body)
}

type jwksDocument struct {
	Keys []json.RawMessage `json:"keys"`
}

type jwkDocumentKey struct {
	KTY string `json:"kty"`
	Use string `json:"use"`
	Kid string `json:"kid"`
	Alg string `json:"alg"`
	N   string `json:"n"`
	E   string `json:"e"`
}

func parseJWKSKeySet(body []byte) (rsaKeySet, error) {
	if len(body) == 0 {
		return nil, errors.New("JWKS response is empty")
	}
	var document jwksDocument
	if err := json.Unmarshal(body, &document); err != nil {
		return nil, fmt.Errorf("JWKS response is not valid JSON: %w", err)
	}
	if len(document.Keys) == 0 {
		return nil, errors.New("JWKS response contains no keys")
	}
	keys := make(rsaKeySet, len(document.Keys))
	for index, rawKey := range document.Keys {
		var key jwkDocumentKey
		if err := json.Unmarshal(rawKey, &key); err != nil {
			return nil, fmt.Errorf("JWKS key %d is invalid: %w", index, err)
		}
		if key.KTY != "RSA" {
			return nil, fmt.Errorf("JWKS key %d has unsupported key type", index)
		}
		if key.Use != "" && key.Use != "sig" {
			return nil, fmt.Errorf("JWKS key %d has unsupported use", index)
		}
		if key.Alg != "" && key.Alg != "RS256" {
			return nil, fmt.Errorf("JWKS key %d has unsupported algorithm", index)
		}
		if !validJWKSKeyID(key.Kid) {
			return nil, fmt.Errorf("JWKS key %d has an invalid kid", index)
		}
		publicKey, err := parseJWKRSAPublicKey(key.N, key.E)
		if err != nil {
			return nil, fmt.Errorf("JWKS key %d is invalid: %w", index, err)
		}
		if _, exists := keys[key.Kid]; exists {
			return nil, fmt.Errorf("JWKS contains duplicate kid %q", key.Kid)
		}
		keys[key.Kid] = publicKey
	}
	return keys, nil
}

func validJWKSKeyID(kid string) bool {
	return kid != "" && len(kid) <= maxJWKSKeyIDLength && strings.TrimSpace(kid) == kid && !strings.ContainsAny(kid, "\r\n\x00")
}

func parseJWKRSAPublicKey(modulusEncoded, exponentEncoded string) (*rsa.PublicKey, error) {
	if modulusEncoded == "" || exponentEncoded == "" {
		return nil, errors.New("RSA key is missing modulus or exponent")
	}
	modulusBytes, err := base64.RawURLEncoding.DecodeString(modulusEncoded)
	if err != nil || len(modulusBytes) == 0 || modulusBytes[0] == 0 {
		return nil, errors.New("RSA modulus is not canonical base64url")
	}
	exponentBytes, err := base64.RawURLEncoding.DecodeString(exponentEncoded)
	if err != nil || len(exponentBytes) == 0 {
		return nil, errors.New("RSA exponent is not valid base64url")
	}
	exponent := new(big.Int).SetBytes(exponentBytes)
	if !exponent.IsInt64() || exponent.Int64() != requiredRSAPublicExponent {
		return nil, errors.New("RSA exponent must be 65537")
	}
	modulus := new(big.Int).SetBytes(modulusBytes)
	key := &rsa.PublicKey{N: modulus, E: requiredRSAPublicExponent}
	if err := validateRSAPublicKey(key); err != nil {
		return nil, err
	}
	return key, nil
}

func validateRSAPublicKey(key *rsa.PublicKey) error {
	if key == nil || key.N == nil || key.N.Sign() <= 0 {
		return errors.New("RSA modulus must be positive")
	}
	if key.N.BitLen() < minimumRSAModulusBits {
		return fmt.Errorf("RSA modulus must be at least %d bits", minimumRSAModulusBits)
	}
	if key.E != requiredRSAPublicExponent {
		return fmt.Errorf("RSA exponent must be %d", requiredRSAPublicExponent)
	}
	return nil
}

// jwtKeyFuncWithKeySet resolves only the exact JOSE kid supplied by a token.
// A static PEM key is accepted as a bounded fallback before the first JWKS
// snapshot, and only under its configured active kid when strict mode is on.
// The variadic final argument preserves the old five-argument test seam while
// allowing strict callers to explicitly reject HMAC when no key is loaded.
func jwtKeyFuncWithKeySet(secret string, rsaPub *rsa.PublicKey, store *rsaKeySetStore, requireKID bool, activeKID string, requireRS256 ...bool) jwt.Keyfunc {
	strictRS256 := len(requireRS256) > 0 && requireRS256[0]
	return func(token *jwt.Token) (interface{}, error) {
		if token == nil {
			return nil, errors.New("JWT token is nil")
		}
		switch token.Method.(type) {
		case *jwt.SigningMethodRSA:
			return resolveRSAJWTKey(token, rsaPub, store, requireKID, activeKID)
		case *jwt.SigningMethodHMAC:
			return resolveHMACJWTKey(token, secret, rsaPub, store, strictRS256)
		default:
			return nil, fmt.Errorf("unexpected signing method: %v", token.Header["alg"])
		}
	}
}

func resolveRSAJWTKey(token *jwt.Token, rsaPub *rsa.PublicKey, store *rsaKeySetStore, requireKID bool, activeKID string) (interface{}, error) {
	if token.Method != jwt.SigningMethodRS256 || token.Method.Alg() != "RS256" {
		return nil, fmt.Errorf("unexpected RSA signing method: %v", token.Header["alg"])
	}
	kid, kidOK := token.Header["kid"].(string)
	if rawKid, exists := token.Header["kid"]; exists && !kidOK {
		return nil, fmt.Errorf("RS256 token has invalid kid type %T", rawKid)
	}
	if store != nil {
		if keys := store.Load(); len(keys) > 0 {
			return resolveJWKSKey(kid, keys, requireKID)
		}
		if store.staleAfter > 0 {
			return nil, errors.New("RS256 JWKS key set is unavailable or stale")
		}
	}
	return resolveStaticRSAKey(kid, rsaPub, requireKID, activeKID)
}

func resolveJWKSKey(kid string, keys rsaKeySet, requireKID bool) (interface{}, error) {
	if kid == "" {
		if requireKID || len(keys) != 1 {
			return nil, errors.New("RS256 token is missing kid")
		}
		for _, key := range keys {
			return key, nil
		}
	}
	if key, ok := keys[kid]; ok {
		return key, nil
	}
	return nil, fmt.Errorf("RS256 token references unknown kid %q", kid)
}

func resolveStaticRSAKey(kid string, rsaPub *rsa.PublicKey, requireKID bool, activeKID string) (interface{}, error) {
	if rsaPub == nil {
		return nil, errors.New("RS256 token received but no RSA public key is available")
	}
	if requireKID {
		if kid == "" {
			return nil, errors.New("RS256 token is missing kid")
		}
		if activeKID == "" || kid != activeKID {
			return nil, fmt.Errorf("RS256 token references unknown kid %q", kid)
		}
	}
	return rsaPub, nil
}

func resolveHMACJWTKey(token *jwt.Token, secret string, rsaPub *rsa.PublicKey, store *rsaKeySetStore, strictRS256 bool) (interface{}, error) {
	if strictRS256 || rsaPub != nil || store.Len() > 0 {
		return nil, errors.New("HS256 token rejected: RS256 is configured")
	}
	if token.Method != jwt.SigningMethodHS256 || token.Method.Alg() != "HS256" {
		return nil, fmt.Errorf("unexpected HMAC signing method: %v", token.Header["alg"])
	}
	if secret == "" {
		return nil, errors.New("HS256 token received but no JWT secret configured")
	}
	return []byte(secret), nil
}
