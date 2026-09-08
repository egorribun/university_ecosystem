//go:build integration

package main

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"sync/atomic"
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
		"nats:2.12.6-alpine@sha256:1cfc36e2e5e638243d8c722f72c954cd0ec4b15ee82fadbc718ce12e2b3c1652",
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
	calls      chan workflow.ProcessJob
	ids        chan string
	callTimes  chan time.Time
	failFirst  atomic.Bool
	callNumber atomic.Int32
}

func (m *integrationTemporalClient) ExecuteWorkflow(
	_ context.Context,
	options client.StartWorkflowOptions,
	_ interface{},
	args ...interface{},
) (client.WorkflowRun, error) {
	n := m.callNumber.Add(1)
	if len(args) == 1 {
		if job, ok := args[0].(workflow.ProcessJob); ok {
			select {
			case m.calls <- job:
			default:
			}
		}
	}
	if m.ids != nil {
		select {
		case m.ids <- options.ID:
		default:
		}
	}
	if m.callTimes != nil {
		select {
		case m.callTimes <- time.Now():
		default:
		}
	}
	if m.failFirst.Load() && n == 1 {
		return nil, errors.New("transient Temporal outage")
	}
	return nil, nil
}

func startFileProcessStream(t *testing.T) (*nats.Conn, nats.JetStreamContext, func()) {
	t.Helper()
	nc, js, cleanup := startFileProcessorJetStream(t)
	_, err := js.AddStream(&nats.StreamConfig{
		Name:      "FILE_EVENTS",
		Subjects:  []string{fileProcessSubject},
		Storage:   nats.MemoryStorage,
		Retention: nats.LimitsPolicy,
	})
	require.NoError(t, err)
	return nc, js, cleanup
}

func validIntegrationJob(id string) workflow.ProcessJob {
	return workflow.ProcessJob{
		ID:        id,
		Type:      "image_resize",
		SourceKey: "input/source.png",
		DestKey:   "output/dest.png",
		Options:   map[string]interface{}{"width": float64(50), "height": float64(50)},
	}
}

func TestIntegration_StartNatsSubscriberExecutesWorkflow(t *testing.T) {
	nc, js, cleanup := startFileProcessStream(t)
	t.Cleanup(cleanup)

	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	calls := make(chan workflow.ProcessJob, 1)
	clientStub := &integrationTemporalClient{calls: calls, ids: make(chan string, 1)}
	cfg := &config.Config{
		NatsURL:     nc.ConnectedUrl(),
		Environment: "testing",
	}
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	startNatsSubscriber(ctx, cfg, clientStub, logger)

	job := validIntegrationJob("integration-job-1")
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
		// Options crosses the JSON wire and is decoded into map[string]any, so
		// numeric values are float64 even though the publisher started with ints.
		require.Len(t, got.Options, 2)
		require.Equal(t, float64(50), got.Options["width"])
		require.Equal(t, float64(50), got.Options["height"])
	case <-time.After(5 * time.Second):
		t.Fatal("timed out waiting for NATS subscriber to execute workflow")
	}
	select {
	case workflowID := <-clientStub.ids:
		require.Equal(t, "file-process-"+job.ID, workflowID)
	case <-time.After(5 * time.Second):
		t.Fatal("timed out waiting for canonical workflow ID")
	}
}

func TestIntegration_StartNatsSubscriberConfiguresBoundedConsumer(t *testing.T) {
	nc, js, cleanup := startFileProcessStream(t)
	t.Cleanup(cleanup)
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	clientStub := &integrationTemporalClient{calls: make(chan workflow.ProcessJob, 1)}
	require.NoError(t, startNatsSubscriber(ctx, &config.Config{NatsURL: nc.ConnectedUrl(), Environment: "testing"}, clientStub, slog.New(slog.NewTextHandler(io.Discard, nil))))
	info, err := js.ConsumerInfo("FILE_EVENTS", fileProcessConsumer)
	require.NoError(t, err)
	require.Equal(t, fileProcessMaxDeliver, info.Config.MaxDeliver)
	require.Equal(t, nats.AckExplicitPolicy, info.Config.AckPolicy)
	require.Equal(t, fileProcessConsumer, info.Config.Durable)
	require.Equal(t, fileProcessSubject, info.Config.FilterSubject)
	require.Equal(t, fileProcessConsumer, info.Config.DeliverGroup)
}

func TestIntegration_StartNatsSubscriberTerminatesPoisonWithoutTemporal(t *testing.T) {
	nc, js, cleanup := startFileProcessStream(t)
	t.Cleanup(cleanup)
	advisorySubject := "$JS.EVENT.ADVISORY.CONSUMER.MSG_TERMINATED.FILE_EVENTS." + fileProcessConsumer
	advisory, err := nc.SubscribeSync(advisorySubject)
	require.NoError(t, err)
	t.Cleanup(func() { _ = advisory.Unsubscribe() })
	require.NoError(t, nc.Flush())

	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	calls := make(chan workflow.ProcessJob, 1)
	clientStub := &integrationTemporalClient{calls: calls}
	require.NoError(t, startNatsSubscriber(ctx, &config.Config{NatsURL: nc.ConnectedUrl(), Environment: "testing"}, clientStub, slog.New(slog.NewTextHandler(io.Discard, nil))))
	_, err = js.Publish(fileProcessSubject, []byte(`not-json`))
	require.NoError(t, err)
	message, err := advisory.NextMsg(10 * time.Second)
	require.NoError(t, err)
	require.Contains(t, string(message.Data), `"consumer":"`+fileProcessConsumer+`"`)
	require.Contains(t, string(message.Data), `"stream":"FILE_EVENTS"`)
	select {
	case <-calls:
		t.Fatal("poison payload must not start Temporal")
	default:
	}
}

func TestIntegration_StartNatsSubscriberTerminatesSemanticPoison(t *testing.T) {
	nc, js, cleanup := startFileProcessStream(t)
	t.Cleanup(cleanup)
	advisorySubject := "$JS.EVENT.ADVISORY.CONSUMER.MSG_TERMINATED.FILE_EVENTS." + fileProcessConsumer
	advisory, err := nc.SubscribeSync(advisorySubject)
	require.NoError(t, err)
	t.Cleanup(func() { _ = advisory.Unsubscribe() })
	require.NoError(t, nc.Flush())
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	calls := make(chan workflow.ProcessJob, 1)
	clientStub := &integrationTemporalClient{calls: calls}
	require.NoError(t, startNatsSubscriber(ctx, &config.Config{NatsURL: nc.ConnectedUrl(), Environment: "testing"}, clientStub, slog.New(slog.NewTextHandler(io.Discard, nil))))
	for _, payload := range []string{`{}`, `{"id":"generic","name":"process_uploaded_file","args":[],"kwargs":{}}`} {
		_, err = js.Publish(fileProcessSubject, []byte(payload))
		require.NoError(t, err)
		_, err = advisory.NextMsg(10 * time.Second)
		require.NoError(t, err)
	}
	select {
	case <-calls:
		t.Fatal("semantic poison payload must not start Temporal")
	default:
	}
}

func TestIntegration_StartNatsSubscriberDelaysTransientRedelivery(t *testing.T) {
	nc, js, cleanup := startFileProcessStream(t)
	t.Cleanup(cleanup)
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	calls := make(chan workflow.ProcessJob, 2)
	callTimes := make(chan time.Time, 2)
	clientStub := &integrationTemporalClient{calls: calls, callTimes: callTimes}
	clientStub.failFirst.Store(true)
	require.NoError(t, startNatsSubscriber(ctx, &config.Config{NatsURL: nc.ConnectedUrl(), Environment: "testing"}, clientStub, slog.New(slog.NewTextHandler(io.Discard, nil))))
	body, err := json.Marshal(validIntegrationJob("transient-job"))
	require.NoError(t, err)
	_, err = js.Publish(fileProcessSubject, body)
	require.NoError(t, err)
	select {
	case <-calls:
	case <-time.After(5 * time.Second):
		t.Fatal("timed out waiting for first Temporal attempt")
	}
	first := <-callTimes
	select {
	case <-calls:
	case <-time.After(12 * time.Second):
		t.Fatal("timed out waiting for delayed redelivery")
	}
	second := <-callTimes
	require.GreaterOrEqual(t, second.Sub(first), fileProcessNakDelay)
	info, err := js.ConsumerInfo("FILE_EVENTS", fileProcessConsumer)
	require.NoError(t, err)
	require.Equal(t, 0, info.NumAckPending)
}

func TestIntegration_StartNatsSubscriberMigratesLegacyDurableInPlace(t *testing.T) {
	nc, js, cleanup := startFileProcessStream(t)
	t.Cleanup(cleanup)
	deliverSubject := nc.NewInbox()
	_, err := js.AddConsumer("FILE_EVENTS", &nats.ConsumerConfig{
		Name:           fileProcessConsumer,
		Durable:        fileProcessConsumer,
		FilterSubject:  fileProcessSubject,
		DeliverPolicy:  nats.DeliverAllPolicy,
		AckPolicy:      nats.AckExplicitPolicy,
		MaxDeliver:     -1,
		DeliverSubject: deliverSubject,
		DeliverGroup:   fileProcessConsumer,
	})
	require.NoError(t, err)
	body, err := json.Marshal(validIntegrationJob("legacy-job"))
	require.NoError(t, err)
	_, err = js.Publish(fileProcessSubject, body)
	require.NoError(t, err)
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	calls := make(chan workflow.ProcessJob, 1)
	clientStub := &integrationTemporalClient{calls: calls}
	require.NoError(t, startNatsSubscriber(ctx, &config.Config{NatsURL: nc.ConnectedUrl(), Environment: "testing"}, clientStub, slog.New(slog.NewTextHandler(io.Discard, nil))))
	info, err := js.ConsumerInfo("FILE_EVENTS", fileProcessConsumer)
	require.NoError(t, err)
	require.Equal(t, fileProcessMaxDeliver, info.Config.MaxDeliver)
	require.Equal(t, deliverSubject, info.Config.DeliverSubject)
	select {
	case <-calls:
	case <-time.After(5 * time.Second):
		t.Fatal("legacy pending message was not delivered after in-place migration")
	}
}
