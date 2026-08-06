package main

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/file-processor/internal/config"
	"go.temporal.io/sdk/client"
)

type fakeLegacyNatsJetStream struct {
	handler      nats.MsgHandler
	subscribeErr error
}

func (f *fakeLegacyNatsJetStream) QueueSubscribe(_ string, _ string, cb nats.MsgHandler, _ ...nats.SubOpt) (*nats.Subscription, error) {
	f.handler = cb
	return nil, f.subscribeErr
}

type fakeLegacyNatsConnection struct {
	js     legacyNatsJetStream
	jsErr  error
	closed chan struct{}
}

func (f *fakeLegacyNatsConnection) JetStream() (legacyNatsJetStream, error) {
	return f.js, f.jsErr
}

func (f *fakeLegacyNatsConnection) Close() {
	select {
	case <-f.closed:
	default:
		close(f.closed)
	}
}

type natsTemporalClientStub struct {
	client.Client
	executeErr error
	calls      chan struct{}
}

func (f *natsTemporalClientStub) ExecuteWorkflow(
	_ context.Context,
	_ client.StartWorkflowOptions,
	_ interface{},
	_ ...interface{},
) (client.WorkflowRun, error) {
	f.calls <- struct{}{}
	return nil, f.executeErr
}

func TestStartNatsSubscriber_MessageBranches(t *testing.T) {
	js := &fakeLegacyNatsJetStream{}
	conn := &fakeLegacyNatsConnection{js: js, closed: make(chan struct{})}
	oldConnect := connectLegacyNats
	connectLegacyNats = func(_ string, _ ...nats.Option) (legacyNatsConnection, error) {
		return conn, nil
	}
	t.Cleanup(func() { connectLegacyNats = oldConnect })

	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	temporal := &natsTemporalClientStub{calls: make(chan struct{}, 2)}
	startNatsSubscriber(ctx, &config.Config{Environment: "production"}, temporal, discardLogger())
	require.NotNil(t, js.handler)

	// Invalid payloads are rejected before Temporal is called.
	js.handler(&nats.Msg{Data: []byte("not-json")})

	// A Temporal failure takes the Nak path.
	temporal.executeErr = errors.New("workflow unavailable")
	js.handler(&nats.Msg{Data: []byte(`{"id":"failed-job"}`)})

	// A successful workflow reaches the Ack path. These synthetic messages have
	// no reply subject, so NATS reports the expected best-effort ack error.
	temporal.executeErr = nil
	js.handler(&nats.Msg{Data: []byte(`{"id":"successful-job"}`)})
	assert.Len(t, temporal.calls, 2)

	cancel()
	require.Eventually(t, func() bool {
		select {
		case <-conn.closed:
			return true
		default:
			return false
		}
	}, time.Second, 10*time.Millisecond)
}

func TestStartNatsSubscriber_ConnectionAndJetStreamErrors(t *testing.T) {
	t.Run("connection error", func(t *testing.T) {
		oldConnect := connectLegacyNats
		connectLegacyNats = func(_ string, _ ...nats.Option) (legacyNatsConnection, error) {
			return nil, errors.New("broker unavailable")
		}
		t.Cleanup(func() { connectLegacyNats = oldConnect })

		assert.NotPanics(t, func() {
			startNatsSubscriber(context.Background(), &config.Config{Environment: "production"}, nil, discardLogger())
		})
	})

	t.Run("JetStream initialization error", func(t *testing.T) {
		conn := &fakeLegacyNatsConnection{
			jsErr:  errors.New("JetStream disabled"),
			closed: make(chan struct{}),
		}
		oldConnect := connectLegacyNats
		connectLegacyNats = func(_ string, _ ...nats.Option) (legacyNatsConnection, error) {
			return conn, nil
		}
		t.Cleanup(func() { connectLegacyNats = oldConnect })

		ctx, cancel := context.WithCancel(context.Background())
		startNatsSubscriber(ctx, &config.Config{Environment: "testing"}, nil, discardLogger())
		cancel()
		require.Eventually(t, func() bool {
			select {
			case <-conn.closed:
				return true
			default:
				return false
			}
		}, time.Second, 10*time.Millisecond)
	})

	t.Run("subscription error", func(t *testing.T) {
		js := &fakeLegacyNatsJetStream{subscribeErr: errors.New("subscribe failed")}
		conn := &fakeLegacyNatsConnection{js: js, closed: make(chan struct{})}
		oldConnect := connectLegacyNats
		connectLegacyNats = func(_ string, _ ...nats.Option) (legacyNatsConnection, error) {
			return conn, nil
		}
		t.Cleanup(func() { connectLegacyNats = oldConnect })

		ctx, cancel := context.WithCancel(context.Background())
		startNatsSubscriber(ctx, &config.Config{Environment: "testing"}, nil, discardLogger())
		require.NotNil(t, js.handler)
		cancel()
		require.Eventually(t, func() bool {
			select {
			case <-conn.closed:
				return true
			default:
				return false
			}
		}, time.Second, 10*time.Millisecond)
	})
}
