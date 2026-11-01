//go:build integration

package hub

import (
	"context"
	"crypto/rand"
	"io"
	"log/slog"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/ws-hub/pkg/config"
)

// TestIntegration_AUD478AdmissionOpensOnlyAfterReplayIsApplied runs the admission
// barrier against a real JetStream server. A revocation published before the
// replica starts must be applied before admission opens, and a revocation older
// than the replay window must not be replayed at all.
func TestIntegration_AUD478AdmissionOpensOnlyAfterReplayIsApplied(t *testing.T) {
	nc, js := startJetStreamNATSContainer(t)
	namespace := integrationNamespace(t)
	stream := "CACHE_INVALIDATIONS_" + strings.ToUpper(namespace)
	addOwnedMemoryStream(t, js, stream, "cache.invalidate", "cache.revoke")

	secret := rand.Text()
	const replayUser = "11111111-aaaa-4aaa-8aaa-111111111111"
	const replayRoom = "22222222-aaaa-4aaa-8aaa-222222222222"
	const liveUser = "33333333-aaaa-4aaa-8aaa-333333333333"
	const liveRoom = "44444444-aaaa-4aaa-8aaa-444444444444"
	const pureUser = "55555555-aaaa-4aaa-8aaa-555555555555"
	const pureRoom = "66666666-aaaa-4aaa-8aaa-666666666666"

	_, err := js.Publish("cache.revoke", signedInvalidationPayload(t, secret, invalidationData{
		EvictRoom: true, RoomID: replayRoom, Timestamp: 1, UserID: replayUser,
	}))
	require.NoError(t, err)
	_, err = js.Publish("cache.invalidate", signedInvalidationPayload(t, secret, invalidationData{
		RoomID: pureRoom, Timestamp: 2, UserID: pureUser,
	}))
	require.NoError(t, err)

	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	cfg := &config.Config{
		MaxClients:                    10,
		BroadcastBufferSize:           10,
		BroadcastWorkers:              1,
		ClientMsgRateLimit:            10,
		ClientMsgRateBurst:            10,
		InternalSecret:                secret,
		RevocationReplayWindowSeconds: 60,
	}
	auth := &recordingAuthClient{}
	h := trackTestHub(NewHub(nc, logger, auth, cfg, nil))
	t.Cleanup(h.Stop)
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	require.NoError(t, h.SubscribeToNATS(ctx))

	require.Eventually(t, func() bool { return !h.RevocationCatchingUp() }, 5*time.Second, 5*time.Millisecond,
		"admission must open once the replay window has drained")
	require.Equal(t, [][2]string{{replayUser, replayRoom}}, auth.calls(),
		"admission may open only after the replayed revocation was applied; pure invalidations are live-only")

	_, err = js.Publish("cache.revoke", signedInvalidationPayload(t, secret, invalidationData{
		EvictRoom: true, RoomID: liveRoom, Timestamp: 3, UserID: liveUser,
	}))
	require.NoError(t, err)
	require.Eventually(t, func() bool { return len(auth.calls()) == 2 }, 5*time.Second, 5*time.Millisecond,
		"revocations published after admission opens must still be applied live")
	require.ElementsMatch(t, [][2]string{{replayUser, replayRoom}, {liveUser, liveRoom}}, auth.calls())

	// A revocation older than the replay window is outside the bounded replay and
	// must not be delivered to a replica that starts now.
	time.Sleep(2 * time.Second)
	shortCfg := *cfg
	shortCfg.RevocationReplayWindowSeconds = 1
	lateAuth := &recordingAuthClient{}
	late := trackTestHub(NewHub(nc, logger, lateAuth, &shortCfg, nil))
	t.Cleanup(late.Stop)
	lateCtx, lateCancel := context.WithCancel(context.Background())
	t.Cleanup(lateCancel)
	require.NoError(t, late.SubscribeToNATS(lateCtx))
	require.Eventually(t, func() bool { return !late.RevocationCatchingUp() }, 5*time.Second, 5*time.Millisecond)
	require.Empty(t, lateAuth.calls(), "revocations older than the replay window must not be replayed")
}

// TestIntegration_AUD478BarrierReclosesWhenReplayConsumerIsDeleted runs the loss path
// against a real JetStream server. Once the replay has drained and admission is open,
// deleting the cache.revoke consumer on the server must close admission again.
func TestIntegration_AUD478BarrierReclosesWhenReplayConsumerIsDeleted(t *testing.T) {
	nc, js := startJetStreamNATSContainer(t)
	namespace := integrationNamespace(t)
	stream := "CACHE_INVALIDATIONS_" + strings.ToUpper(namespace)
	addOwnedMemoryStream(t, js, stream, "cache.invalidate", "cache.revoke")

	secret := rand.Text()
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	cfg := &config.Config{
		MaxClients:                    10,
		BroadcastBufferSize:           10,
		BroadcastWorkers:              1,
		ClientMsgRateLimit:            10,
		ClientMsgRateBurst:            10,
		InternalSecret:                secret,
		RevocationReplayWindowSeconds: 60,
	}
	h := trackTestHub(NewHub(nc, logger, &recordingAuthClient{}, cfg, nil))
	t.Cleanup(h.Stop)
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	require.NoError(t, h.SubscribeToNATS(ctx))
	require.Eventually(t, func() bool { return !h.RevocationCatchingUp() }, 5*time.Second, 5*time.Millisecond)

	// A push subscription's Subject is its delivery inbox, so the revocation consumer
	// is identified by the filter subject of its consumer configuration.
	var revokeConsumer string
	for _, sub := range h.subs {
		info, err := sub.ConsumerInfo()
		if err == nil && info.Config.FilterSubject == "cache.revoke" {
			revokeConsumer = info.Name
		}
	}
	require.NotEmpty(t, revokeConsumer, "the cache.revoke consumer must be bound")
	require.NoError(t, js.DeleteConsumer(stream, revokeConsumer))

	require.Eventually(t, func() bool { return h.RevocationCatchingUp() }, 5*time.Second, 5*time.Millisecond,
		"losing the replay consumer on the server must close admission")
}
