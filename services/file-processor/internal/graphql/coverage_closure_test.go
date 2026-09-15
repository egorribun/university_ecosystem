package graphql

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
	pb "github.com/university-ecosystem/core/gen/go/file_processor/v1"
	"go.temporal.io/sdk/client"
)

type replayGuardError struct{}

func (replayGuardError) Consume(context.Context, string, time.Time) (bool, error) {
	return false, errors.New("replay registry unavailable")
}

func TestResolverProcessFileKeepsAcceptedWorkflowWhenReplayAdmissionFails(t *testing.T) {
	now := time.Now().UTC()
	input := mintResolverCapabilityInputAt(t, now)
	ctx := pb.WithProcessingIdentity(context.Background(), pb.ProcessingIdentity{
		UserID: "u-1", SessionID: "session-1",
	})
	r := &Resolver{
		RequireCapability: true,
		CapabilitySecret:  []byte(resolverCapabilityKey),
		ReplayGuard:       replayGuardError{},
		Now:               func() time.Time { return now },
		TemporalClient: &fakeTemporalClient{executeFunc: func(context.Context, client.StartWorkflowOptions, interface{}, ...interface{}) (client.WorkflowRun, error) {
			return &fakeWorkflowRun{id: "accepted-without-replay-record"}, nil
		}},
	}

	job, err := r.ProcessFile(ctx, struct{ Input ProcessFileInput }{Input: input})
	require.NoError(t, err)
	require.Equal(t, "accepted-without-replay-record", string(job.JobID()))
}
