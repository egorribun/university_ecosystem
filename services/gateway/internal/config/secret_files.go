package config

import (
	"errors"
	"io"
	"os"
	"strings"
	"unicode"
	"unicode/utf8"
)

const maxSecretFileSize = 64 * 1024

// readSecretEnv reads KEY_FILE when configured, otherwise preserving the
// existing KEY environment-variable contract used by Compose. A configured
// file is authoritative: unreadable or invalid files never fall back to env.
func readSecretEnv(key string) (value string, configured bool, err error) {
	filePath, fileConfigured := os.LookupEnv(key + "_FILE")
	if fileConfigured {
		if strings.TrimSpace(filePath) == "" {
			return "", true, errors.New(key + "_FILE must not be empty")
		}
		contents, readErr := readSecretFile(filePath)
		if readErr != nil {
			return "", true, errors.New(key + "_FILE: " + readErr.Error())
		}
		value, valueErr := secretFileValue(contents)
		if valueErr != nil {
			return "", true, errors.New(key + "_FILE: " + valueErr.Error())
		}
		return value, true, nil
	}
	value, configured = os.LookupEnv(key)
	return value, configured, nil
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

type secretFileOpenFunc func(string) (*os.File, error)
type secretFileReadFunc func(*os.File) ([]byte, error)

func readSecretFile(path string) ([]byte, error) {
	return readSecretFileWithIO(path, openSecretFile, readBoundedSecretFile)
}

// readSecretFileWithIO keeps the file checks and bounded read in one path while
// allowing deterministic tests for filesystem races and descriptor failures.
func readSecretFileWithIO(path string, openFile secretFileOpenFunc, readFile secretFileReadFunc) (contents []byte, err error) {
	pathInfo, err := os.Stat(path)
	if err != nil {
		return nil, errors.New("cannot inspect configured secret file")
	}
	if !pathInfo.Mode().IsRegular() {
		return nil, errors.New("configured secret path must resolve to a regular file")
	}
	file, err := openFile(path)
	if err != nil {
		return nil, errors.New("cannot open configured secret file")
	}
	defer func() {
		if closeErr := file.Close(); closeErr != nil && err == nil {
			contents = nil
			err = errors.New("cannot close configured secret file")
		}
	}()

	info, err := file.Stat()
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
	contents, err = readFile(file)
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
func readBoundedSecretFile(file *os.File) ([]byte, error) {
	return io.ReadAll(io.LimitReader(file, maxSecretFileSize+1))
}
