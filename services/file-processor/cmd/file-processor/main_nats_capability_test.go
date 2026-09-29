package main

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
	pb "github.com/university-ecosystem/core/gen/go/file_processor/v1"
	"github.com/university-ecosystem/file-processor/internal/workflow"
	"go.temporal.io/api/enums/v1"
	"go.temporal.io/api/serviceerror"
)

var natsCapabilityKey = strings.Repeat("k", 32)

func natsCapabilityJob() workflow.ProcessJob {
	return workflow.ProcessJob{
		ID:        "nats-capability-job",
		Type:      "image_resize",
		SourceKey: "input/nats.png",
		DestKey:   "output/nats.png",
		Options:   map[string]interface{}{"width": 100},
	}
}

func natsCapabilityPayload(t *testing.T, job workflow.ProcessJob, secret []byte, issuedAt time.Time) []byte {
	t.Helper()
	token, err := pb.MintProcessingCapabilityAt(secret, pb.ProcessingCapabilityClaims{
		ID:        job.ID,
		Type:      job.Type,
		SourceKey: job.SourceKey,
		DestKey:   job.DestKey,
		UserID:    "user-1",
		SessionID: "session-1",
		ExpiresAt: issuedAt.Add(5 * time.Minute).Unix(),
		Nonce:     "nats-capability-nonce",
	}, issuedAt)
	require.NoError(t, err)
	job.Capability = token
	payload, err := json.Marshal(job)
	require.NoError(t, err)
	return payload
}

func TestHandleFileProcessDelivery_RejectsInvalidCapability(t *testing.T) {
	issuedAt := time.Now().UTC()
	baseJob := natsCapabilityJob()
	tests := []struct {
		name       string
		payload    func() []byte
		secret     []byte
		wantReason string
	}{
		{
			name: "missing capability",
			payload: func() []byte {
				payload, err := json.Marshal(baseJob)
				require.NoError(t, err)
				return payload
			},
			secret: []byte(natsCapabilityKey),
		},
		{
			name: "wrong signing key",
			payload: func() []byte {
				return natsCapabilityPayload(t, baseJob, []byte(strings.Repeat("m", 32)), issuedAt)
			},
			secret: []byte(natsCapabilityKey),
		},
		{
			name: "request binding mismatch",
			payload: func() []byte {
				payload := natsCapabilityPayload(t, baseJob, []byte(natsCapabilityKey), issuedAt)
				var job workflow.ProcessJob
				require.NoError(t, json.Unmarshal(payload, &job))
				job.DestKey = "output/other.png"
				payload, err := json.Marshal(job)
				require.NoError(t, err)
				return payload
			},
			secret: []byte(natsCapabilityKey),
		},
		{
			name: "expired capability",
			payload: func() []byte {
				issuerTime := issuedAt.Add(-5 * time.Minute)
				job := baseJob
				// Minting relative to the historical issuer time is valid, while
				// the current consumer clock must reject the already-expired proof.
				token, err := pb.MintProcessingCapabilityAt([]byte(natsCapabilityKey), pb.ProcessingCapabilityClaims{
					ID: job.ID, Type: job.Type, SourceKey: job.SourceKey, DestKey: job.DestKey,
					UserID: "user-1", SessionID: "session-1", ExpiresAt: issuedAt.Add(-time.Minute).Unix(),
					Nonce: "expired-nats-capability",
				}, issuerTime)
				require.NoError(t, err)
				job.Capability = token
				payload, err := json.Marshal(job)
				require.NoError(t, err)
				return payload
			},
			secret: []byte(natsCapabilityKey),
		},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			msg := &fakeProcessDeliveryMessage{payload: tc.payload()}
			stub := &natsTemporalClientStub{calls: make(chan struct{}, 1)}
			handleFileProcessDelivery(context.Background(), msg, stub, discardLogger(), tc.secret)
			require.Equal(t, 1, msg.termCount)
			require.Zero(t, msg.ackCount)
			require.Zero(t, msg.nakCount)
			require.Empty(t, stub.options)
		})
	}
}

func TestHandleFileProcessDelivery_AcceptsCapabilityAndRejectsDuplicateWorkflow(t *testing.T) {
	job := natsCapabilityJob()
	payload := natsCapabilityPayload(t, job, []byte(natsCapabilityKey), time.Now().UTC())
	stub := &natsTemporalClientStub{calls: make(chan struct{}, 2)}
	first := &fakeProcessDeliveryMessage{payload: payload}
	handleFileProcessDelivery(context.Background(), first, stub, discardLogger(), []byte(natsCapabilityKey))
	require.Equal(t, 1, first.ackCount)
	require.Zero(t, first.termCount)
	require.Zero(t, first.nakCount)
	require.Len(t, stub.options, 1)
	require.Len(t, stub.jobs, 1)
	require.Empty(t, stub.jobs[0].Capability, "bearer capabilities must not enter Temporal history")
	require.Equal(t, enums.WORKFLOW_ID_REUSE_POLICY_REJECT_DUPLICATE, stub.options[0].WorkflowIDReusePolicy)

	// A redelivered capability is not allowed to start another execution: the
	// deterministic Temporal workflow ID and reject-duplicate policy turn replay
	// into an idempotent acknowledgement.
	stub.executeErr = serviceerror.NewWorkflowExecutionAlreadyStarted("already started", "request", "run")
	second := &fakeProcessDeliveryMessage{payload: payload}
	handleFileProcessDelivery(context.Background(), second, stub, discardLogger(), []byte(natsCapabilityKey))
	require.Equal(t, 1, second.ackCount)
	require.Zero(t, second.termCount)
	require.Zero(t, second.nakCount)
	require.Len(t, stub.options, 2)
}

func TestHandleFileProcessDelivery_TemporalFailureDoesNotBurnCapability(t *testing.T) {
	job := natsCapabilityJob()
	payload := natsCapabilityPayload(t, job, []byte(natsCapabilityKey), time.Now().UTC())
	registry := pb.NewCapabilityReplayRegistry(4)
	stub := &natsTemporalClientStub{
		executeErr: errors.New("temporal unavailable"),
		calls:      make(chan struct{}, 2),
	}
	first := &fakeProcessDeliveryMessage{payload: payload}
	handleFileProcessDelivery(context.Background(), first, stub, discardLogger(), []byte(natsCapabilityKey), registry)
	require.Zero(t, first.ackCount)
	require.Equal(t, 1, first.nakCount)

	stub.executeErr = nil
	second := &fakeProcessDeliveryMessage{payload: payload}
	handleFileProcessDelivery(context.Background(), second, stub, discardLogger(), []byte(natsCapabilityKey), registry)
	require.Equal(t, 1, second.ackCount)
	require.Zero(t, second.nakCount)
	require.Len(t, stub.options, 2)
	require.Len(t, stub.jobs, 2)
	require.Empty(t, stub.jobs[1].Capability, "bearer capabilities must not enter Temporal history")
}

func TestHandleFileProcessDelivery_CapabilityFailureDoesNotRetry(t *testing.T) {
	msg := &fakeProcessDeliveryMessage{payload: natsCapabilityPayload(t, natsCapabilityJob(), []byte(natsCapabilityKey), time.Now().UTC()), termErr: errors.New("term failed")}
	var temporal natsTemporalClientStub
	handleFileProcessDelivery(context.Background(), msg, &temporal, discardLogger(), []byte("short"))
	require.Equal(t, 1, msg.termCount)
	require.Equal(t, 1, msg.nakCount, "termination failure is retried through the bounded fallback")
	require.Equal(t, []time.Duration{fileProcessNakDelay}, msg.nakDelays)
}

func TestHandleFileProcessDelivery_RedeliveryUsesTemporalIdempotency(t *testing.T) {
	job := natsCapabilityJob()
	payload := natsCapabilityPayload(t, job, []byte(natsCapabilityKey), time.Now().UTC())
	registry := pb.NewCapabilityReplayRegistry(4)
	stub := &natsTemporalClientStub{calls: make(chan struct{}, 2)}
	first := &fakeProcessDeliveryMessage{payload: payload}
	handleFileProcessDelivery(context.Background(), first, stub, discardLogger(), []byte(natsCapabilityKey), registry)
	require.Equal(t, 1, first.ackCount)
	require.Len(t, stub.options, 1)
	second := &fakeProcessDeliveryMessage{payload: payload}
	handleFileProcessDelivery(context.Background(), second, stub, discardLogger(), []byte(natsCapabilityKey), registry)
	require.Equal(t, 1, second.ackCount)
	require.Zero(t, second.termCount)
	require.Len(t, stub.options, 2, "the deterministic Temporal workflow ID is checked on each redelivery")
}
