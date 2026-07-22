//go:build contract

// Package contract_test contains Pact V4 provider verification for the
// backend -> file-processor synchronous ProcessFile boundary.
package contract_test

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	"github.com/pact-foundation/pact-go/v2/message"
	"github.com/pact-foundation/pact-go/v2/models"
	"github.com/pact-foundation/pact-go/v2/provider"
	pb "github.com/university-ecosystem/core/gen/go/file_processor/v1"
	"github.com/university-ecosystem/file-processor/internal/service"
	"go.temporal.io/sdk/client"
)

const contractJobID = "550e8400-e29b-41d4-a716-446655440002"

type contractWorkflowRun struct {
	client.WorkflowRun
}

func (contractWorkflowRun) GetID() string { return contractJobID }

type contractTemporalClient struct {
	client.Client
}

func (contractTemporalClient) ExecuteWorkflow(
	context.Context,
	client.StartWorkflowOptions,
	interface{},
	...interface{},
) (client.WorkflowRun, error) {
	return contractWorkflowRun{}, nil
}

func processFileResponse(_ []models.ProviderState) (message.Body, message.Metadata, error) {
	server := &service.Server{TemporalClient: contractTemporalClient{}}
	response, err := server.ProcessFile(context.Background(), &pb.ProcessFileRequest{
		Id:          contractJobID,
		Type:        "image_resize",
		SourceKey:   "uploads/raw/img.jpg",
		DestKey:     "uploads/processed/img.jpg",
		Options:     map[string]string{"width": "800"},
		CallbackUrl: "http://backend/callback",
	})
	if err != nil {
		return nil, nil, err
	}

	return map[string]interface{}{
			"job_id":      response.JobId,
			"success":     response.Success,
			"dest_key":    response.DestKey,
			"duration_ms": response.DurationMs,
		}, message.Metadata{
			"contentType": "application/grpc",
		}, nil
}

func TestProcessFileMessageProvider(t *testing.T) {
	pactDir := os.Getenv("PACT_DIR")
	if pactDir == "" {
		pactDir = filepath.Join("..", "..", "..", "..", "tests", "contracts", "pacts")
	}

	verifier := provider.NewVerifier()
	if err := verifier.VerifyProvider(t, provider.VerifyRequest{
		Provider: "file-processor",
		PactFiles: []string{
			filepath.ToSlash(filepath.Join(pactDir, "university-backend-file-processor.json")),
		},
		MessageHandlers: message.Handlers{
			"a gRPC request for ProcessFile": processFileResponse,
		},
	}); err != nil {
		t.Fatalf("Pact verification failed: %v", err)
	}
}
