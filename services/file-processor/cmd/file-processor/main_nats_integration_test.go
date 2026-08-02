//go:build integration

package main

import (
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"testing"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/stretchr/testify/require"
	"github.com/testcontainers/testcontainers-go"
	tclog "github.com/testcontainers/testcontainers-go/log"
	tcnats "github.com/testcontainers/testcontainers-go/modules/nats"
	"github.com/university-ecosystem/file-processor/internal/config"
	"github.com/university-ecosystem/file-processor/internal/workflow"
	"go.temporal.io/sdk/client"
)

func startFileProcessorJetStream(t *testing.T) (*nats.Conn, nats.JetStreamContext, func()) {
	t.Helper()
	ctx := context.Background()

	container, err := tcnats.Run(
		ctx,
		"nats:2.12.6-alpine",
		tcnats.WithArgument("jetstream", ""),
		testcontainers.WithLogger(tclog.TestLogger(t)),
	)
	require.NoError(t, err)

	connectionString, err := container.ConnectionString(ctx)
	if err != nil {
		_ = container.Terminate(ctx)
		t.Fatalf("JetStream NATS connection string: %v", err)
	}

	nc, err := nats.Connect(connectionString)
	if err != nil {
		_ = container.Terminate(ctx)
		t.Fatalf("JetStream NATS connect: %v", err)
	}
	js, err := nc.JetStream()
	if err != nil {
		nc.Close()
		_ = container.Terminate(ctx)
		t.Fatalf("JetStream context: %v", err)
	}

	cleanup := func() {
		nc.Close()
		if err := container.Terminate(context.Background()); err != nil {
			t.Logf("JetStream NATS container cleanup: %v", err)
		}
	}
	return nc, js, cleanup
}

type integrationTemporalClient struct {
	client.Client
	calls chan workflow.ProcessJob
}

func (m *integrationTemporalClient) ExecuteWorkflow(
	_ context.Context,
	_ client.StartWorkflowOptions,
	_ interface{},
	args ...interface{},
) (client.WorkflowRun, error) {
	if len(args) == 1 {
		if job, ok := args[0].(workflow.ProcessJob); ok {
			m.calls <- job
		}
	}
	return nil, nil
}

func TestIntegration_StartNatsSubscriberExecutesWorkflow(t *testing.T) {
	nc, js, cleanup := startFileProcessorJetStream(t)
	t.Cleanup(cleanup)

	_, err := js.AddStream(&nats.StreamConfig{
		Name:      "FILE_EVENTS",
		Subjects:  []string{"files.process"},
		Storage:   nats.MemoryStorage,
		Retention: nats.LimitsPolicy,
	})
	require.NoError(t, err)

	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	calls := make(chan workflow.ProcessJob, 1)
	clientStub := &integrationTemporalClient{calls: calls}
	cfg := &config.Config{
		NatsURL:     nc.ConnectedUrl(),
		Environment: "testing",
	}
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	startNatsSubscriber(ctx, cfg, clientStub, logger)

	job := workflow.ProcessJob{
		ID:        "integration-job-1",
		Type:      "image_resize",
		SourceKey: "input/source.png",
		DestKey:   "output/dest.png",
		Options:   map[string]interface{}{"width": 50, "height": 50},
	}
	body, err := json.Marshal(job)
	require.NoError(t, err)
	_, err = js.Publish("files.process", body)
	require.NoError(t, err)

	select {
	case got := <-calls:
		require.Equal(t, job.ID, got.ID)
		require.Equal(t, job.Type, got.Type)
		require.Equal(t, job.SourceKey, got.SourceKey)
		require.Equal(t, job.DestKey, got.DestKey)
		require.Equal(t, job.Options, got.Options)
	case <-time.After(5 * time.Second):
		t.Fatal("timed out waiting for NATS subscriber to execute workflow")
	}
}
