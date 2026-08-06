package tlsutil

import (
	"crypto/rand"
	"crypto/tls"
	"errors"
	"io"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

type failAfterBlockReader struct {
	source        io.Reader
	allowedBlocks int
}

func (r *failAfterBlockReader) Read(p []byte) (int, error) {
	// crypto/rand's custom-reader compatibility path may make a
	// nondeterministic one-byte probe. Count only the fixed-size entropy blocks
	// used by key, serial, and certificate generation.
	if len(p) > 1 {
		if r.allowedBlocks == 0 {
			return 0, errors.New("entropy unavailable")
		}
		r.allowedBlocks--
	}
	return r.source.Read(p)
}

func TestGenerateSelfSignedTLSCert(t *testing.T) {
	cfg, err := GenerateSelfSignedTLSCert()
	require.NoError(t, err)
	require.NotNil(t, cfg)

	assert.Equal(t, uint16(tls.VersionTLS13), cfg.MinVersion)
	assert.Len(t, cfg.Certificates, 1)
	assert.NotEmpty(t, cfg.Certificates[0].Certificate)
	assert.NotNil(t, cfg.Certificates[0].PrivateKey)
}

func TestGenerateSelfSignedTLSCert_EntropyFailures(t *testing.T) {
	// Go 1.26 uses the system CSPRNG for ECDSA key generation by default and
	// ignores a custom reader unless this compatibility switch is enabled.
	t.Setenv("GODEBUG", "cryptocustomrand=1")

	tests := []struct {
		name          string
		allowedBlocks int
		wantError     string
	}{
		{name: "key generation", allowedBlocks: 0, wantError: "generate P256 key"},
		{name: "serial generation", allowedBlocks: 1, wantError: "generate serial number"},
		{name: "certificate generation", allowedBlocks: 2, wantError: "create certificate"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			cfg, err := generateSelfSignedTLSCert(&failAfterBlockReader{
				source:        rand.Reader,
				allowedBlocks: tt.allowedBlocks,
			})
			require.Error(t, err)
			require.Nil(t, cfg)
			assert.Contains(t, err.Error(), tt.wantError)
		})
	}
}
