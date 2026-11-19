package middleware

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"sync"
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

type jwksLimitRoundTripper func(*http.Request) (*http.Response, error)

func (f jwksLimitRoundTripper) RoundTrip(req *http.Request) (*http.Response, error) {
	return f(req)
}

type jwksLimitObservedBody struct {
	io.ReadCloser
	readBytes int
	waiting   chan struct{}
	closed    chan struct{}
	waitOnce  sync.Once
	closeOnce sync.Once
}

func (b *jwksLimitObservedBody) Read(p []byte) (int, error) {
	if b.readBytes == 64*1024 && b.waiting != nil {
		b.waitOnce.Do(func() { close(b.waiting) })
	}
	n, err := b.ReadCloser.Read(p)
	b.readBytes += n
	return n, err
}

func (b *jwksLimitObservedBody) Close() error {
	err := b.ReadCloser.Close()
	b.closeOnce.Do(func() { close(b.closed) })
	return err
}

func TestJWKSBodyLimitClosesResponse(t *testing.T) {
	for _, size := range []int{64 * 1024, 64*1024 + 1} {
		t.Run(strconv.Itoa(size), func(t *testing.T) {
			body := &jwksLimitObservedBody{
				ReadCloser: io.NopCloser(strings.NewReader(strings.Repeat(" ", size))),
				closed:     make(chan struct{}),
			}
			client := &http.Client{Transport: jwksLimitRoundTripper(func(req *http.Request) (*http.Response, error) {
				return &http.Response{StatusCode: http.StatusOK, Body: body, Header: make(http.Header), Request: req}, nil
			})}
			result, err := fetchJWKSBody(context.Background(), client, "https://jwks.example.test/keys")
			if size == 64*1024 {
				require.NoError(t, err)
				require.Len(t, result, size)
			} else {
				require.ErrorContains(t, err, "exceeds 64 KiB limit")
				require.Nil(t, result)
			}
			select {
			case <-body.closed:
			default:
				t.Fatal("response body was not closed")
			}
		})
	}
}

func TestJWKSBodyLimitCancellationWhileAwaitingSentinel(t *testing.T) {
	release := make(chan struct{})
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		// No Content-Length and no final chunk: the next read must wait for
		// the sentinel byte or EOF, not treat this valid prefix as complete.
		w.(http.Flusher).Flush()
		_, _ = io.WriteString(w, "{}"+strings.Repeat(" ", 64*1024-2))
		w.(http.Flusher).Flush()
		select {
		case <-req.Context().Done():
		case <-release:
		}
	}))
	t.Cleanup(server.Close)
	t.Cleanup(func() { close(release) })

	waiting := make(chan struct{})
	closed := make(chan struct{})
	transport := &http.Transport{}
	t.Cleanup(transport.CloseIdleConnections)
	client := (&JWTMiddleware{}).newJWKSHTTPClient()
	require.Equal(t, 10*time.Second, client.Timeout)
	client.Transport = jwksLimitRoundTripper(func(req *http.Request) (*http.Response, error) {
		resp, err := transport.RoundTrip(req)
		if err == nil {
			resp.Body = &jwksLimitObservedBody{ReadCloser: resp.Body, waiting: waiting, closed: closed}
		}
		return resp, err
	})
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	done := make(chan error, 1)
	go func() {
		_, err := fetchJWKSBody(ctx, client, server.URL)
		done <- err
	}()
	select {
	case <-waiting:
	case err := <-done:
		t.Fatalf("fetch finished before reading sentinel: %v", err)
	case <-time.After(5 * time.Second):
		t.Fatal("fetch did not reach sentinel read")
	}
	cancel()
	select {
	case err := <-done:
		require.ErrorIs(t, err, context.Canceled)
	case <-time.After(5 * time.Second):
		t.Fatal("request cancellation did not interrupt sentinel read")
	}
	select {
	case <-closed:
	default:
		t.Fatal("cancelled response body was not closed")
	}
	require.Equal(t, 10*time.Second, client.Timeout)
}
