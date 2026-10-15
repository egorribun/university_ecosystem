package config

import (
	"errors"
	"io"
	"os"
	"strings"
	"unicode"
	"unicode/utf8"

	"github.com/spf13/viper"
)

const maxSecretFileSize = 64 * 1024

type secretFileOperations struct {
	statPath func(string) (os.FileInfo, error)
	open     func(string) (*os.File, error)
	statFile func(*os.File) (os.FileInfo, error)
	read     func(*os.File, int64) ([]byte, error)
	close    func(*os.File) error
}

var secretFileIO = secretFileOperations{
	statPath: os.Stat,
	open:     openSecretFile,
	statFile: func(file *os.File) (os.FileInfo, error) { return file.Stat() },
	read: func(file *os.File, limit int64) ([]byte, error) {
		return io.ReadAll(io.LimitReader(file, limit))
	},
	close: func(file *os.File) error { return file.Close() },
}

func readSecretFile(path string) (result []byte, resultErr error) {
	if path == "" {
		return nil, errors.New("configured secret file path must not be empty")
	}
	pathInfo, err := secretFileIO.statPath(path)
	if err != nil {
		return nil, errors.New("cannot inspect configured secret file")
	}
	if !pathInfo.Mode().IsRegular() {
		return nil, errors.New("configured secret path must resolve to a regular file")
	}
	file, err := secretFileIO.open(path)
	if err != nil {
		return nil, errors.New("cannot open configured secret file")
	}
	defer func() {
		if closeErr := secretFileIO.close(file); closeErr != nil {
			result = nil
			if resultErr == nil {
				resultErr = errors.New("cannot close configured secret file")
			}
		}
	}()

	info, err := secretFileIO.statFile(file)
	if err != nil {
		return nil, errors.New("cannot inspect configured secret file")
	}
	// Stat follows the projected-volume symlinks used by Kubernetes Secret
	// volumes while still rejecting directories, FIFOs, and device files.
	if !info.Mode().IsRegular() {
		return nil, errors.New("configured secret path must resolve to a regular file")
	}
	if info.Size() > maxSecretFileSize {
		return nil, errors.New("configured secret file exceeds the size limit")
	}
	contents, err := secretFileIO.read(file, maxSecretFileSize+1)
	if err != nil {
		return nil, errors.New("cannot read configured secret file")
	}
	if len(contents) > maxSecretFileSize {
		return nil, errors.New("configured secret file exceeds the size limit")
	}
	if len(contents) == 0 {
		return nil, errors.New("configured secret file must not be empty")
	}
	if !utf8.Valid(contents) {
		return nil, errors.New("configured secret file must contain UTF-8 text")
	}
	return contents, nil
}

// secretFileValue matches the backend's one-line _FILE credential semantics:
// surrounding whitespace (including a projected-file newline) is ignored, but
// embedded control characters are rejected. Plain Compose environment values
// bypass this function and retain their existing exact-byte behavior.
func secretFileValue(contents []byte) (string, error) {
	value := strings.TrimSpace(string(contents))
	if value == "" || strings.IndexFunc(value, unicode.IsControl) >= 0 {
		return "", errors.New("configured secret file must contain one non-empty line")
	}
	return value, nil
}

func applySecretFileOverrides() error {
	for _, item := range []struct {
		key string
		env string
	}{
		{key: "nats_url", env: "FP_NATS_URL"},
		{key: "minio_access_key", env: "FP_MINIO_ACCESS_KEY"},
		{key: "minio_secret_key", env: "FP_MINIO_SECRET_KEY"},
		{key: "processing_capability_secret", env: "FP_PROCESSING_CAPABILITY_SECRET"},
		{key: "jwt_secret", env: "FP_JWT_SECRET"},
		{key: "revocation_redis_url", env: "FP_REVOCATION_REDIS_URL"},
	} {
		path, configured := os.LookupEnv(item.env + "_FILE")
		if !configured {
			continue
		}
		contents, err := readSecretFile(path)
		if err != nil {
			return errors.New(item.env + "_FILE: " + err.Error())
		}
		value, valueErr := secretFileValue(contents)
		if valueErr != nil {
			return errors.New(item.env + "_FILE: " + valueErr.Error())
		}
		viper.Set(item.key, value)
	}
	return nil
}
