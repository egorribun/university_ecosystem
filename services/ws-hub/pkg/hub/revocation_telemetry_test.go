package hub

import (
	"bytes"
	"context"
	"fmt"
	"log/slog"
	"testing"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/sdk/trace/tracetest"
)

func TestRoomRevocationRetryOmitsIdentifiersFromTelemetry(t *testing.T) {
	const user = "synthetic-account"
	const room = "synthetic-conversation"

	h := setupTestHub()
	t.Cleanup(h.Stop)
	h.authClient = &controlledRoomMembershipAuth{refresh: func(_ context.Context, user, room string) (bool, error) {
		return false, fmt.Errorf("synthetic upstream error for %s in %s", user, room)
	}}
	var logs bytes.Buffer
	h.Logger = slog.New(slog.NewJSONHandler(&logs, nil))

	originalNak := jetStreamNakFunc
	t.Cleanup(func() { jetStreamNakFunc = originalNak })
	var retries []time.Duration
	jetStreamNakFunc = func(_ *nats.Msg, delay time.Duration) error {
		retries = append(retries, delay)
		return nil
	}

	recorder := tracetest.NewSpanRecorder()
	provider := sdktrace.NewTracerProvider(sdktrace.WithSampler(sdktrace.AlwaysSample()), sdktrace.WithSpanProcessor(recorder))
	t.Cleanup(func() { require.NoError(t, provider.Shutdown(context.Background())) })
	ctx, span := provider.Tracer("hub-test").Start(t.Context(), "room revocation")
	var payload cacheInvalidationPayload
	payload.Data.EvictRoom = true
	payload.Data.UserID = user
	payload.Data.RoomID = room

	assert.False(t, h.applyCacheInvalidation(ctx, &nats.Msg{Subject: "cache.revoke"}, span, payload))
	span.End()
	assert.Equal(t, []time.Duration{5 * time.Second}, retries)

	assert.Contains(t, logs.String(), "Room membership revocation could not be confirmed; retrying")
	assert.NotContains(t, logs.String(), user)
	assert.NotContains(t, logs.String(), room)

	ended := recorder.Ended()
	require.Len(t, ended, 1)
	events := ended[0].Events()
	require.Len(t, events, 1)
	assert.Equal(t, "exception", events[0].Name)
	for _, attr := range events[0].Attributes {
		assert.NotContains(t, attr.Value.String(), user)
		assert.NotContains(t, attr.Value.String(), room)
	}
}
