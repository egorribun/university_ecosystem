package tlsutil

import (
	"crypto/tls"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestGenerateSelfSignedTLSCert(t *testing.T) {
	cfg, err := GenerateSelfSignedTLSCert()
	require.NoError(t, err)
	require.NotNil(t, cfg)

	assert.Equal(t, uint16(tls.VersionTLS13), cfg.MinVersion)
	assert.Len(t, cfg.Certificates, 1)
	assert.NotEmpty(t, cfg.Certificates[0].Certificate)
	assert.NotNil(t, cfg.Certificates[0].PrivateKey)
}
