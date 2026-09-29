package graphql

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	pb "github.com/university-ecosystem/core/gen/go/file_processor/v1"
	"github.com/university-ecosystem/file-processor/internal/workflow"
	"go.temporal.io/api/serviceerror"
	"go.temporal.io/sdk/client"
)

var resolverCapabilityKey = strings.Repeat("k", 32)

func resolverCapabilityInput(t *testing.T) (ProcessFileInput, context.Context) {
	t.Helper()
	now := time.Unix(1_700_000_000, 0)
	input := ProcessFileInput{
		Type:      "image_resize",
		SourceKey: "users/u-1/source.png",
		DestKey:   "users/u-1/dest.png",
	}
	token, err := pb.MintProcessingCapabilityAt([]byte(resolverCapabilityKey), pb.ProcessingCapabilityClaims{
		ID:        "graphql-capability-job",
		Type:      input.Type,
		SourceKey: input.SourceKey,
		DestKey:   input.DestKey,
		UserID:    "u-1",
		SessionID: "session-1",
		ExpiresAt: now.Add(5 * time.Minute).Unix(),
		Nonce:     "graphql-capability-nonce",
	}, now)
	require.NoError(t, err)
	input.Capability = token
	return input, pb.WithProcessingIdentity(context.Background(), pb.ProcessingIdentity{UserID: "u-1", SessionID: "session-1"})
}

func TestResolverProcessFile_RequiresCapabilityBeforeTemporal(t *testing.T) {
	called := false
	r := &Resolver{
		RequireCapability: true,
		CapabilitySecret:  []byte(resolverCapabilityKey),
		TemporalClient: &fakeTemporalClient{executeFunc: func(context.Context, client.StartWorkflowOptions, interface{}, ...interface{}) (client.WorkflowRun, error) {
			called = true
			return &fakeWorkflowRun{id: "unexpected"}, nil
		}},
	}
	_, err := r.ProcessFile(context.Background(), struct{ Input ProcessFileInput }{Input: ProcessFileInput{
		Type: "image_resize", SourceKey: "src/a.png", DestKey: "dst/a.png",
	}})
	require.Error(t, err)
	assert.Contains(t, err.Error(), "authorization required")
	assert.False(t, called)
}

func TestResolverProcessFile_ValidCapabilityBindsWorkflowIDAndKeys(t *testing.T) {
	input, ctx := resolverCapabilityInput(t)
	var captured workflow.ProcessJob
	r := &Resolver{
		RequireCapability: true,
		CapabilitySecret:  []byte(resolverCapabilityKey),
		Now:               func() time.Time { return time.Unix(1_700_000_000, 0) },
		TemporalClient: &fakeTemporalClient{executeFunc: func(_ context.Context, _ client.StartWorkflowOptions, _ interface{}, args ...interface{}) (client.WorkflowRun, error) {
			captured = args[0].(workflow.ProcessJob)
			return &fakeWorkflowRun{id: "graphql-accepted"}, nil
		}},
	}
	job, err := r.ProcessFile(ctx, struct{ Input ProcessFileInput }{Input: input})
	require.NoError(t, err)
	assert.Equal(t, "graphql-accepted", string(job.JobID()))
	assert.Equal(t, "graphql-capability-job", captured.ID)
	assert.Equal(t, input.SourceKey, captured.SourceKey)
	assert.Equal(t, input.DestKey, captured.DestKey)
	assert.Empty(t, captured.Capability, "bearer capabilities must not enter Temporal history")
}

func TestResolverProcessFile_RejectsCapabilityKeyMismatch(t *testing.T) {
	input, ctx := resolverCapabilityInput(t)
	input.DestKey = "users/u-1/other.png"
	r := &Resolver{
		RequireCapability: true,
		CapabilitySecret:  []byte(resolverCapabilityKey),
		Now:               func() time.Time { return time.Unix(1_700_000_000, 0) },
		TemporalClient:    &fakeTemporalClient{},
	}
	_, err := r.ProcessFile(ctx, struct{ Input ProcessFileInput }{Input: input})
	require.Error(t, err)
	assert.Contains(t, err.Error(), "authorization required")
}

func TestResolverProcessFile_RejectsCapabilityReplay(t *testing.T) {
	registry := pb.NewCapabilityReplayRegistry(4)
	calls := 0
	// The helper's fixed clock is used by the capability verifier; use a fresh
	// capability below so the replay registry's production wall clock also sees
	// it as live.
	now := time.Now().UTC()
	input := mintResolverCapabilityInputAt(t, now)
	ctx := pb.WithProcessingIdentity(context.Background(), pb.ProcessingIdentity{UserID: "u-1", SessionID: "session-1"})
	r := &Resolver{
		RequireCapability: true,
		CapabilitySecret:  []byte(resolverCapabilityKey),
		ReplayGuard:       registry,
		Now:               func() time.Time { return now },
		TemporalClient: &fakeTemporalClient{executeFunc: func(_ context.Context, options client.StartWorkflowOptions, _ interface{}, _ ...interface{}) (client.WorkflowRun, error) {
			calls++
			assert.Equal(t, "file-process-graphql-replay-job", options.ID)
			if calls > 1 {
				return nil, serviceerror.NewWorkflowExecutionAlreadyStarted("already started", "request", "run")
			}
			return &fakeWorkflowRun{id: "graphql-replay-guarded"}, nil
		}},
	}
	first, err := r.ProcessFile(ctx, struct{ Input ProcessFileInput }{Input: input})
	require.NoError(t, err)
	require.Equal(t, "graphql-replay-guarded", string(first.JobID()))
	second, err := r.ProcessFile(ctx, struct{ Input ProcessFileInput }{Input: input})
	require.NoError(t, err)
	require.NotNil(t, second)
	require.Equal(t, "file-process-graphql-replay-job", string(second.JobID()))
	require.Equal(t, "STARTED", second.Status())
	require.Equal(t, 2, calls, "Temporal deterministic workflow ID is the replay authority")
}

func TestResolverProcessFile_TemporalFailureDoesNotBurnCapability(t *testing.T) {
	now := time.Now().UTC()
	input := mintResolverCapabilityInputAt(t, now)
	ctx := pb.WithProcessingIdentity(context.Background(), pb.ProcessingIdentity{UserID: "u-1", SessionID: "session-1"})
	registry := pb.NewCapabilityReplayRegistry(4)
	attempts := 0
	r := &Resolver{
		RequireCapability: true,
		CapabilitySecret:  []byte(resolverCapabilityKey),
		ReplayGuard:       registry,
		Now:               func() time.Time { return now },
		TemporalClient: &fakeTemporalClient{executeFunc: func(context.Context, client.StartWorkflowOptions, interface{}, ...interface{}) (client.WorkflowRun, error) {
			attempts++
			if attempts == 1 {
				return nil, errors.New("temporal unavailable")
			}
			return &fakeWorkflowRun{id: "graphql-retried-after-temporal-failure"}, nil
		}},
	}
	_, err := r.ProcessFile(ctx, struct{ Input ProcessFileInput }{Input: input})
	require.Error(t, err)
	_, err = r.ProcessFile(ctx, struct{ Input ProcessFileInput }{Input: input})
	require.NoError(t, err)
	require.Equal(t, 2, attempts)
	accepted, replayErr := registry.ConsumeAt(
		context.Background(),
		"graphql-replay-nonce",
		now.Add(5*time.Minute),
		now,
	)
	require.NoError(t, replayErr)
	require.False(t, accepted, "successful retry must record the capability after workflow start")
}

func mintResolverCapabilityInputAt(t *testing.T, now time.Time) ProcessFileInput {
	t.Helper()
	input := ProcessFileInput{Type: "image_resize", SourceKey: "users/u-1/source.png", DestKey: "users/u-1/dest.png"}
	token, err := pb.MintProcessingCapabilityAt([]byte(resolverCapabilityKey), pb.ProcessingCapabilityClaims{
		ID: "graphql-replay-job", Type: input.Type, SourceKey: input.SourceKey, DestKey: input.DestKey,
		UserID: "u-1", SessionID: "session-1", ExpiresAt: now.Add(5 * time.Minute).Unix(), Nonce: "graphql-replay-nonce",
	}, now)
	require.NoError(t, err)
	input.Capability = token
	return input
}
