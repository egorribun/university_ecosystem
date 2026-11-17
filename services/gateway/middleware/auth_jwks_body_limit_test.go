package middleware

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

func TestJWKSBodyLimitRejectsTruncatedValidPrefix(t *testing.T) {
	key, pemText := rsaTestKeys(t)
	formats := map[string]string{
		"json": string(rsaJWKSBody(t, &key.PublicKey)),
		"pem":  pemText,
	}
	const limit = 64 * 1024
	for format, prefix := range formats {
		for _, size := range []int{limit - 1, limit, limit + 1} {
			for _, chunked := range []bool{false, true} {
				name := fmt.Sprintf("%s/size=%d/chunked=%t", format, size, chunked)
				t.Run(name, func(t *testing.T) {
					body := prefix + strings.Repeat(" ", size-len(prefix))
					server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
						if chunked {
							w.(http.Flusher).Flush()
						} else {
							w.Header().Set("Content-Length", strconv.Itoa(len(body)))
						}
						if _, err := io.WriteString(w, body); err != nil {
							t.Errorf("write bounded JWKS fixture: %v", err)
						}
					}))
					t.Cleanup(server.Close)
					keys, err := fetchJWKSKeySet(context.Background(), server.Client(), server.URL)
					if size > limit {
						require.ErrorContains(t, err, "exceeds 64 KiB limit")
						require.Nil(t, keys)
						return
					}
					require.NoError(t, err)
					require.Len(t, keys, 1)
					for _, parsed := range keys {
						require.Equal(t, key.N, parsed.N)
					}
				})
			}
		}
	}
}

func TestOversizedJWKSRefreshPreservesKeysAndFreshness(t *testing.T) {
	key, _ := rsaTestKeys(t)
	prefix := string(rsaJWKSBody(t, &key.PublicKey))
	const limit = 64 * 1024
	body := prefix + strings.Repeat(" ", limit-len(prefix)) + "x"
	// The first 64 KiB is valid JSON. The actual response is not.
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.(http.Flusher).Flush()
		if _, err := io.WriteString(w, body); err != nil {
			t.Errorf("write oversized JWKS fixture: %v", err)
		}
	}))
	t.Cleanup(server.Close)
	middleware := &JWTMiddleware{}
	publishedAt := time.Now().UTC().Add(-time.Hour)
	middleware.storeRSAKeysAt(rsaKeySet{"original": &key.PublicKey}, publishedAt)
	original := middleware.jwksSnapshot.Load()

	rotated, err := middleware.refreshJWKSOnce(context.Background(), server.Client(), server.URL)

	require.ErrorContains(t, err, "exceeds 64 KiB limit")
	require.False(t, rotated)
	require.Same(t, original, middleware.jwksSnapshot.Load())
	require.Equal(t, publishedAt, middleware.jwksSnapshot.Load().fetchedAt)
}
