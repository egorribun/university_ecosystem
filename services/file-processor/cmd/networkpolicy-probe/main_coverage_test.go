package main

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"errors"
	"flag"
	"math/big"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// These fixtures exercise client setup only. They are not evidence that the
// actual file-processor or its deployment accepts or denies any request.
func setupCredentialFiles(t *testing.T) (string, string) {
	t.Helper()
	public, private, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	now := time.Now()
	template := &x509.Certificate{
		SerialNumber: big.NewInt(2), Subject: pkix.Name{CommonName: "setup-fixture"},
		NotBefore: now.Add(-time.Minute), NotAfter: now.Add(time.Hour),
		IsCA: true, BasicConstraintsValid: true,
		KeyUsage: x509.KeyUsageCertSign | x509.KeyUsageDigitalSignature,
	}
	der, err := x509.CreateCertificate(rand.Reader, template, template, public, private)
	if err != nil {
		t.Fatal(err)
	}
	key, err := x509.MarshalPKCS8PrivateKey(private)
	if err != nil {
		t.Fatal(err)
	}
	directory := t.TempDir()
	certificatePath := filepath.Join(directory, "client.crt")
	keyPath := filepath.Join(directory, "client.key")
	for path, data := range map[string][]byte{
		certificatePath: pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der}),
		keyPath:         pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: key}),
	} {
		if err := os.WriteFile(path, data, 0600); err != nil {
			t.Fatal(err)
		}
	}
	return certificatePath, keyPath
}

func TestProbeSetupErrorsAreSanitized(t *testing.T) {
	certificatePath, keyPath := setupCredentialFiles(t)
	missingPath := filepath.Join(t.TempDir(), "absent")
	badPEMPath := filepath.Join(t.TempDir(), "invalid.pem")
	if err := os.WriteFile(badPEMPath, []byte("fixture-invalid-pem-do-not-disclose"), 0600); err != nil {
		t.Fatal(err)
	}
	valid := request{
		Address: "127.0.0.1:1", ServerName: "fixture.test", CAFile: certificatePath,
		CertificateFile: certificatePath, KeyFile: keyPath, Token: "fixture-token-do-not-disclose",
	}
	for name, change := range map[string]func(*request){
		"missing-address":     func(input *request) { input.Address = "" },
		"missing-server-name": func(input *request) { input.ServerName = "" },
		"missing-token":       func(input *request) { input.Token = "" },
		"missing-ca":          func(input *request) { input.CAFile = missingPath },
		"invalid-ca":          func(input *request) { input.CAFile = badPEMPath },
		"missing-certificate": func(input *request) { input.CertificateFile = missingPath },
		"invalid-certificate": func(input *request) { input.CertificateFile = badPEMPath },
		"missing-key":         func(input *request) { input.KeyFile = missingPath },
		"invalid-key":         func(input *request) { input.KeyFile = badPEMPath },
		// grpc.NewClient parses the target before making any connection. An
		// invalid URI escape fails even after its default-scheme fallback.
		"invalid-grpc-target": func(input *request) { input.Address = "%" },
	} {
		t.Run(name, func(t *testing.T) {
			input := valid
			change(&input)
			if observed := probe(context.Background(), input); observed != (result{Result: "setup-error"}) {
				t.Fatalf("unexpected safe result: %+v", observed)
			}
		})
	}
}

func TestMainWritesOnlySafeJSON(t *testing.T) {
	directory := t.TempDir()
	input, err := os.Create(filepath.Join(directory, "stdin"))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = input.Close() })
	if _, err := input.WriteString(`{"unknown":"fixture-do-not-disclose"}`); err != nil {
		t.Fatal(err)
	}
	if _, err := input.Seek(0, 0); err != nil {
		t.Fatal(err)
	}
	output, err := os.Create(filepath.Join(directory, "stdout"))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = output.Close() })
	oldInput, oldOutput := os.Stdin, os.Stdout
	os.Stdin, os.Stdout = input, output
	defer func() { os.Stdin, os.Stdout = oldInput, oldOutput }()
	main()
	if _, err := output.Seek(0, 0); err != nil {
		t.Fatal(err)
	}
	var observed bytes.Buffer
	if _, err := observed.ReadFrom(output); err != nil {
		t.Fatal(err)
	}
	if observed.String() != "{\"result\":\"setup-error\"}\n" {
		t.Fatal("main did not emit exactly the sanitized JSON result")
	}
}

const outputFailureHelperEnvironment = "FP_NETWORKPOLICY_PROBE_OUTPUT_FAILURE_HELPER"

func TestMainOutputFailureExitsSafely(t *testing.T) {
	executable, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	command := exec.CommandContext(ctx, executable, "-test.run=^TestMainOutputFailureProcess$")
	command.Stdin = strings.NewReader(`{"unknown":"fixture-do-not-disclose"}`)
	command.Env = append(os.Environ(), outputFailureHelperEnvironment+"=1")
	if testing.CoverMode() != "" {
		// The actual main below calls os.Exit(1). Go's coverage exit hooks
		// preserve those counters in the same directory the parent test
		// harness consumes when it generates its final coverage profile.
		// No production seam or synthetic coverage is needed.
		directory := flag.Lookup("test.gocoverdir").Value.String()
		if directory == "" {
			// Standalone covered test binaries may omit -test.gocoverdir.
			// Retain child coverage without introducing a stderr warning;
			// normal go test -coverprofile supplies the shared directory.
			directory = t.TempDir()
		}
		command.Env = append(command.Env, "GOCOVERDIR="+directory)
	}
	var stdout, stderr bytes.Buffer
	command.Stdout, command.Stderr = &stdout, &stderr
	err = command.Run()
	var exitError *exec.ExitError
	if !errors.As(err, &exitError) || exitError.ExitCode() != 1 {
		t.Fatalf("expected main exit status 1, got %v", err)
	}
	if stdout.Len() != 0 || stderr.String() != "probe output failed\n" {
		t.Fatal("main output failure was not exactly the sanitized stderr message")
	}
}

func TestMainOutputFailureProcess(t *testing.T) {
	if os.Getenv(outputFailureHelperEnvironment) != "1" {
		return
	}
	if err := os.Stdout.Close(); err != nil {
		t.Fatal("could not close helper stdout")
	}
	main()
	t.Fatal("main returned instead of exiting after its output failed")
}
