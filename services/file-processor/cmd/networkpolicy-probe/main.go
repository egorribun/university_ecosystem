// Command networkpolicy-probe performs one non-mutating authenticated ProcessFile
// request in the existing NetworkPolicy harness. Configuration and bearer tokens
// arrive on stdin; only a bounded gRPC status code is written to stdout.
package main

import (
	"bytes"
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"time"

	pb "github.com/university-ecosystem/core/gen/go/file_processor/v1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
)

type request struct {
	Address         string `json:"address"`
	ServerName      string `json:"server_name"`
	CAFile          string `json:"ca_file"`
	CertificateFile string `json:"certificate_file"`
	KeyFile         string `json:"key_file"`
	Token           string `json:"token"`
}

type result struct {
	Result string `json:"result"`
	Code   string `json:"code,omitempty"`
}

func probe(ctx context.Context, input request) result {
	if input.Address == "" || input.ServerName == "" || input.Token == "" {
		return result{Result: "setup-error"}
	}
	ca, err := os.ReadFile(input.CAFile)
	if err != nil {
		return result{Result: "setup-error"}
	}
	roots := x509.NewCertPool()
	if !roots.AppendCertsFromPEM(ca) {
		return result{Result: "setup-error"}
	}
	certificate, err := tls.LoadX509KeyPair(input.CertificateFile, input.KeyFile)
	if err != nil {
		return result{Result: "setup-error"}
	}
	connection, err := grpc.NewClient(input.Address, grpc.WithTransportCredentials(credentials.NewTLS(&tls.Config{
		MinVersion: tls.VersionTLS13, RootCAs: roots, ServerName: input.ServerName,
		Certificates: []tls.Certificate{certificate},
	})))
	if err != nil {
		return result{Result: "setup-error"}
	}
	defer func() { _ = connection.Close() }()
	deadline, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	deadline = metadata.AppendToOutgoingContext(deadline, "authorization", "Bearer "+input.Token)
	_, err = pb.NewFileProcessingServiceClient(connection).ProcessFile(deadline, &pb.ProcessFileRequest{})
	// A healthy authenticated call must reach empty-request validation and return
	// InvalidArgument. OK, transport errors and all other statuses are NOT success.
	return result{Result: "grpc-status", Code: status.Code(err).String()}
}

func run(input io.Reader, output io.Writer) error {
	raw, err := io.ReadAll(io.LimitReader(input, 65537))
	if err != nil || len(raw) > 65536 {
		return json.NewEncoder(output).Encode(result{Result: "setup-error"})
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	var command request
	if err := decoder.Decode(&command); err != nil {
		return json.NewEncoder(output).Encode(result{Result: "setup-error"})
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		return json.NewEncoder(output).Encode(result{Result: "setup-error"})
	}
	return json.NewEncoder(output).Encode(probe(context.Background(), command))
}

func main() {
	if err := run(os.Stdin, os.Stdout); err != nil {
		// Never print errors that might contain request or credential details.
		_, _ = fmt.Fprintln(os.Stderr, "probe output failed")
		os.Exit(1)
	}
}
