package main

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

func TestHandleFileProcessDelivery_NeverPersistsCapabilityInTemporalInput(t *testing.T) {
	tests := []struct {
		name    string
		prepare func(t *testing.T) ([]byte, []byte)
	}{
		{
			name: "capability verification configured",
			prepare: func(t *testing.T) ([]byte, []byte) {
				job := natsCapabilityJob()
				secret := []byte(natsCapabilityKey)
				return natsCapabilityPayload(t, job, secret, time.Now().UTC()), secret
			},
		},
		{
			name: "capability verification not configured",
			prepare: func(t *testing.T) ([]byte, []byte) {
				job := natsCapabilityJob()
				job.Capability = "synthetic-capability-for-persistence-test"
				payload, err := json.Marshal(job)
				require.NoError(t, err)
				return payload, nil
			},
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			payload, secret := tc.prepare(t)
			msg := &fakeProcessDeliveryMessage{payload: payload}
			stub := &natsTemporalClientStub{calls: make(chan struct{}, 1)}

			handleFileProcessDelivery(context.Background(), msg, stub, discardLogger(), secret)

			require.Equal(t, 1, msg.ackCount)
			require.Zero(t, msg.termCount)
			require.Zero(t, msg.nakCount)
			require.Len(t, stub.jobs, 1)
			require.Empty(t, stub.jobs[0].Capability, "bearer capability must never enter Temporal input/history")
		})
	}
}
