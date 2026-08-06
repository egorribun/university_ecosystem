package tlsutil

import (
	"crypto/rand"
	"crypto/tls"
	"errors"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

type failingRandomReader struct{}

func (failingRandomReader) Read([]byte) (int, error) {
	return 0, errors.New("entropy unavailable")
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

func TestGenerateSelfSignedTLSCert_EntropyFailure(t *testing.T) {
	originalReader := rand.Reader
	rand.Reader = failingRandomReader{}
	t.Cleanup(func() { rand.Reader = originalReader })

	cfg, err := GenerateSelfSignedTLSCert()
	assert.Error(t, err)
	assert.Nil(t, cfg)
	assert.Contains(t, err.Error(), "generate serial number")
}
