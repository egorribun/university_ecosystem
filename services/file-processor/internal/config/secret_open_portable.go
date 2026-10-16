package config

import (
	"os"
	"path/filepath"
)

// openSecretFilePlatform defaults to the portable implementation. Unix builds
// replace it during package initialization with a nonblocking opener.
var openSecretFilePlatform = openSecretFilePortable

// openSecretFile is stable so package-level IO tables can capture it before
// Unix initialization while each call still uses the selected platform opener.
func openSecretFile(path string) (*os.File, error) {
	return openSecretFilePlatform(path)
}

// openSecretFilePortable is kept in the common source set so Linux coverage can
// exercise the fallback implementation too.
func openSecretFilePortable(path string) (*os.File, error) {
	resolvedPath, err := filepath.EvalSymlinks(path)
	if err != nil {
		return nil, err
	}
	return os.OpenInRoot(filepath.Dir(resolvedPath), filepath.Base(resolvedPath))
}
