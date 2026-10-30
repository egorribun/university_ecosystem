package hub

import (
	"context"
	"encoding/json"
	"strings"
	"sync"
	"testing"

	"github.com/nats-io/nats.go"
	"github.com/stretchr/testify/require"
)

// AUD-478: CACHE_INVALIDATIONS retains seven days of events. A replica starts
// with an empty authorization cache, so its invalidation consumer must begin at
// new messages and must not claim a durable identity shared by stateless pods.
func TestAUD478CacheInvalidationConsumerStartsAtNewMessagesWithoutDurableIdentity(t *testing.T) {
	server := newMockNatsServer(t)
	var mu sync.Mutex
	var consumerRequests [][]byte
	server.jetStreamResponder = func(subject string, payload []byte) []byte {
		switch {
		case subject == "$JS.API.STREAM.NAMES":
			return []byte(`{"type":"io.nats.jetstream.api.v1.stream_names_response","total":1,"offset":0,"limit":1024,"streams":["CACHE_INVALIDATIONS"]}`)
		case strings.HasPrefix(subject, "$JS.API.CONSUMER.CREATE.CACHE_INVALIDATIONS"):
			mu.Lock()
			consumerRequests = append(consumerRequests, append([]byte(nil), payload...))
			mu.Unlock()
			return []byte(`{"type":"io.nats.jetstream.api.v1.consumer_create_response","error":{"code":500,"err_code":10000,"description":"captured by test"}}`)
		default:
			return []byte(`{"type":"io.nats.jetstream.api.v1.consumer_create_response","error":{"code":404,"err_code":10059,"description":"unexpected JetStream request"}}`)
		}
	}
	nc, err := nats.Connect(server.Addr())
	require.NoError(t, err)
	t.Cleanup(nc.Close)

	h := setupTestHub()
	h.Nats = nc
	// Core chat and notification subscriptions succeed first, so the only
	// JetStream consumer creation is the cache invalidation consumer under test.
	h.enableJetStream = false
	h.subscribeCacheInvalidations = nil

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	// The captured creation is rejected on purpose; the subscription never exists.
	require.Error(t, h.SubscribeToNATS(ctx))

	mu.Lock()
	requests := consumerRequests
	mu.Unlock()
	require.Len(t, requests, 1)
	var request struct {
		Config map[string]any `json:"config"`
	}
	require.NoError(t, json.Unmarshal(requests[0], &request))
	require.NotContains(t, request.Config, "durable_name", "invalidations must use an ephemeral consumer")
	require.Equal(t, "new", request.Config["deliver_policy"],
		"a restarted replica must not replay CACHE_INVALIDATIONS history")
	require.NotContains(t, request.Config, "opt_start_seq")
	require.Equal(t, "explicit", request.Config["ack_policy"])
}
