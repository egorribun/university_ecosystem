package main

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"io"
	"net"
	"strconv"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/file-processor/internal/config"
	"go.temporal.io/sdk/client"
)

// Observe the real SDK's first bytes, not just the options passed to a mock.
// The synthetic peer closes after reading the preface; it is not a Temporal server.
func TestAUD369ConfiguredTemporalTransportWithoutAPIKey(t *testing.T) {
	for _, tc := range []struct {
		name        string
		environment string
		plaintext   bool
	}{
		{name: "production sends a TLS client hello", environment: "production"},
		{name: "development explicitly uses plaintext", environment: "development", plaintext: true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			listener, err := net.Listen("tcp", "127.0.0.1:0")
			require.NoError(t, err)
			t.Cleanup(func() { require.NoError(t, listener.Close()) })

			var randomSecret [32]byte
			_, err = rand.Read(randomSecret[:])
			require.NoError(t, err)
			t.Setenv("FP_ENVIRONMENT", tc.environment)
			t.Setenv("FP_TEMPORAL_HOST", listener.Addr().String())
			t.Setenv("FP_TEMPORAL_TLS_DISABLED", strconv.FormatBool(tc.plaintext))
			t.Setenv("FP_TEMPORAL_API_KEY_FILE", "")
			t.Setenv("FP_MINIO_ACCESS_KEY", "access")
			t.Setenv("FP_MINIO_SECRET_KEY", hex.EncodeToString(randomSecret[:]))
			t.Setenv("FP_MINIO_SECURE", "true")
			t.Setenv("FP_OTLP_INSECURE", "false")
			t.Setenv("FP_SPIFFE_ENABLED", "true")
			t.Setenv("FP_PROCESSING_CAPABILITY_SECRET", hex.EncodeToString(randomSecret[:]))
			t.Setenv("FP_JWT_SECRET", "")
			t.Setenv("FP_RSA_PUBLIC_KEY_PEM", "")
			t.Setenv("FP_RSA_PUBLIC_KEY_FILE", "")
			t.Setenv("FP_JWKS_URL", "https://issuer.example/.well-known/jwks.json")

			cfg, err := config.Load()
			require.NoError(t, err)
			require.Empty(t, cfg.TemporalAPIKeyFile)

			type prefaceResult struct {
				data [5]byte
				err  error
			}
			observed := make(chan prefaceResult, 1)
			dialCtx, cancelDial := context.WithTimeout(context.Background(), 10*time.Second)
			defer cancelDial()
			go func() {
				defer cancelDial()
				conn, acceptErr := listener.Accept()
				if acceptErr != nil {
					observed <- prefaceResult{err: acceptErr}
					return
				}
				defer conn.Close()
				if deadlineErr := conn.SetReadDeadline(time.Now().Add(5 * time.Second)); deadlineErr != nil {
					observed <- prefaceResult{err: deadlineErr}
					return
				}
				var result prefaceResult
				_, result.err = io.ReadFull(conn, result.data[:])
				observed <- result
			}()

			previousDial := dialTemporalFunc
			t.Cleanup(func() { dialTemporalFunc = previousDial })
			dialTemporalFunc = func(options client.Options) (client.Client, error) {
				return client.DialContext(dialCtx, options)
			}
			outerCtx, cancelOuter := context.WithCancel(context.Background())
			cancelOuter() // stop the application's retry loop after the real dial
			_, err = connectTemporal(outerCtx, cfg, discardLogger())
			require.Error(t, err)

			select {
			case result := <-observed:
				require.NoError(t, result.err)
				if tc.plaintext {
					require.Equal(t, "PRI *", string(result.data[:]))
				} else {
					require.Equal(t, byte(0x16), result.data[0], "expected TLS handshake record")
					require.Equal(t, byte(0x03), result.data[1], "expected TLS record version")
				}
			case <-time.After(time.Second):
				t.Fatal("Temporal SDK did not send a transport preface")
			}
		})
	}
}
