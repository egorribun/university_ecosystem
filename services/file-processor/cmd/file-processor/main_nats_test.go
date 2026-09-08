package main

import (
	"bytes"
	"context"
	"errors"
	"log/slog"
	"strings"
	"testing"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/file-processor/internal/config"
	"go.temporal.io/api/serviceerror"
	"go.temporal.io/sdk/client"
)

type fakeLegacyNatsJetStream struct {
	handler          nats.MsgHandler
	subscribeErr     error
	streamName       string
	streamErr        error
	consumerInfo     *nats.ConsumerInfo
	consumerInfoErr  error
	returnNilInfo    bool
	nilInfoOnLookup  int
	lookupErrs       []error
	updateErrs       []error
	applyUpdateOnErr bool
	updatedConfigs   []*nats.ConsumerConfig
	lookupCount      int
	updateCount      int
	subject          string
	queue            string
	subscribeOptions int
}

func (f *fakeLegacyNatsJetStream) QueueSubscribe(subject, queue string, cb nats.MsgHandler, opts ...nats.SubOpt) (*nats.Subscription, error) {
	f.handler = cb
	f.subject = subject
	f.queue = queue
	f.subscribeOptions = len(opts)
	return nil, f.subscribeErr
}

func (f *fakeLegacyNatsJetStream) StreamNameBySubject(_ string, _ ...nats.JSOpt) (string, error) {
	if f.streamErr != nil {
		return "", f.streamErr
	}
	if f.streamName == "" {
		return "FILE_EVENTS", nil
	}
	return f.streamName, nil
}

func (f *fakeLegacyNatsJetStream) ConsumerInfo(_, _ string, _ ...nats.JSOpt) (*nats.ConsumerInfo, error) {
	f.lookupCount++
	if f.nilInfoOnLookup > 0 && f.lookupCount == f.nilInfoOnLookup {
		return nil, nil
	}
	if len(f.lookupErrs) > 0 {
		err := f.lookupErrs[0]
		f.lookupErrs = f.lookupErrs[1:]
		return f.consumerInfo, err
	}
	if f.consumerInfoErr != nil {
		return f.consumerInfo, f.consumerInfoErr
	}
	if f.returnNilInfo {
		return nil, nil
	}
	if f.consumerInfo == nil {
		return nil, nats.ErrConsumerNotFound
	}
	return f.consumerInfo, nil
}

func (f *fakeLegacyNatsJetStream) UpdateConsumer(_ string, cfg *nats.ConsumerConfig, _ ...nats.JSOpt) (*nats.ConsumerInfo, error) {
	f.updateCount++
	copyCfg := *cfg
	f.updatedConfigs = append(f.updatedConfigs, &copyCfg)
	if len(f.updateErrs) > 0 {
		err := f.updateErrs[0]
		f.updateErrs = f.updateErrs[1:]
		if err != nil {
			if f.applyUpdateOnErr {
				f.consumerInfo = &nats.ConsumerInfo{Config: copyCfg}
			}
			return nil, err
		}
	}
	f.consumerInfo = &nats.ConsumerInfo{Config: copyCfg}
	return f.consumerInfo, nil
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
	options    []client.StartWorkflowOptions
}

func (f *natsTemporalClientStub) ExecuteWorkflow(
	_ context.Context,
	options client.StartWorkflowOptions,
	_ interface{},
	_ ...interface{},
) (client.WorkflowRun, error) {
	f.options = append(f.options, options)
	f.calls <- struct{}{}
	return nil, f.executeErr
}

type fakeProcessDeliveryMessage struct {
	payload   []byte
	ackErr    error
	nakErr    error
	termErr   error
	ackCount  int
	nakCount  int
	termCount int
	nakDelays []time.Duration
}

func (m *fakeProcessDeliveryMessage) Payload() []byte { return m.payload }
func (m *fakeProcessDeliveryMessage) Ack() error {
	m.ackCount++
	return m.ackErr
}
func (m *fakeProcessDeliveryMessage) NakWithDelay(delay time.Duration) error {
	m.nakCount++
	m.nakDelays = append(m.nakDelays, delay)
	return m.nakErr
}
func (m *fakeProcessDeliveryMessage) Term() error {
	m.termCount++
	return m.termErr
}

func validProcessPayload() []byte {
	return []byte(`{"id":"job-1","type":"image_resize","source_key":"input/a.png","dest_key":"output/a.png","options":{"width":100}}`)
}

func TestHandleFileProcessDelivery_Protocol(t *testing.T) {
	tests := []struct {
		name       string
		payload    []byte
		executeErr error
		termErr    error
		wantAck    int
		wantTerm   int
		wantNak    int
		wantDelay  bool
	}{
		{name: "malformed terminates", payload: []byte("not-json"), wantTerm: 1},
		{name: "trailing value terminates", payload: append(validProcessPayload(), []byte(` {}`)...), wantTerm: 1},
		{name: "trailing malformed value terminates", payload: append(validProcessPayload(), []byte(` {`)...), wantTerm: 1},
		{name: "unknown field terminates", payload: []byte(`{"id":"job","type":"image_resize","source_key":"in","dest_key":"out","stale":true}`), wantTerm: 1},
		{name: "semantic poison terminates", payload: []byte(`{"id":"job","type":"unknown","source_key":"in","dest_key":"out"}`), wantTerm: 1},
		{name: "temporal failure delayed", payload: validProcessPayload(), executeErr: errors.New("temporal unavailable"), wantNak: 1, wantDelay: true},
		{name: "success acknowledges", payload: validProcessPayload(), wantAck: 1},
		{name: "term failure falls back", payload: []byte("not-json"), termErr: errors.New("term unavailable"), wantTerm: 1, wantNak: 1, wantDelay: true},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			msg := &fakeProcessDeliveryMessage{payload: test.payload, termErr: test.termErr}
			stub := &natsTemporalClientStub{executeErr: test.executeErr, calls: make(chan struct{}, 1)}
			logger := discardLogger()
			handleFileProcessDelivery(context.Background(), msg, stub, logger)
			require.Equal(t, test.wantAck, msg.ackCount)
			require.Equal(t, test.wantTerm, msg.termCount)
			require.Equal(t, test.wantNak, msg.nakCount)
			if test.wantDelay {
				require.Equal(t, []time.Duration{fileProcessNakDelay}, msg.nakDelays)
			}
			if test.executeErr == nil && test.wantAck == 1 {
				require.Len(t, stub.options, 1)
				require.Equal(t, "file-process-job-1", stub.options[0].ID)
			}
		})
	}
}

func TestHandleFileProcessDelivery_AlreadyStartedIsSuccessfulHandoff(t *testing.T) {
	msg := &fakeProcessDeliveryMessage{payload: validProcessPayload()}
	stub := &natsTemporalClientStub{
		executeErr: serviceerror.NewWorkflowExecutionAlreadyStarted("already started", "request", "run"),
		calls:      make(chan struct{}, 1),
	}
	handleFileProcessDelivery(context.Background(), msg, stub, discardLogger())
	require.Equal(t, 1, msg.ackCount)
	require.Zero(t, msg.nakCount)
	require.Equal(t, "file-process-job-1", stub.options[0].ID)
}

func TestHandleFileProcessDelivery_AckFailureIsDelayedAndDoesNotChangeWorkflowID(t *testing.T) {
	msg := &fakeProcessDeliveryMessage{payload: validProcessPayload(), ackErr: errors.New("ack failed")}
	stub := &natsTemporalClientStub{calls: make(chan struct{}, 1)}
	handleFileProcessDelivery(context.Background(), msg, stub, discardLogger())
	require.Equal(t, 1, msg.ackCount)
	require.Equal(t, 1, msg.nakCount)
	require.Equal(t, []time.Duration{fileProcessNakDelay}, msg.nakDelays)
	require.Equal(t, "file-process-job-1", stub.options[0].ID)
}

func TestHandleFileProcessDelivery_PanicIsRecoveredAndDelayed(t *testing.T) {
	msg := &fakeProcessDeliveryMessage{payload: validProcessPayload()}
	var logs bytes.Buffer
	logger := slog.New(slog.NewTextHandler(&logs, nil))
	// A nil client triggers the callback's panic recovery after validation.
	handleFileProcessDelivery(context.Background(), msg, nil, logger)
	require.Equal(t, 1, msg.nakCount)
	require.Equal(t, []time.Duration{fileProcessNakDelay}, msg.nakDelays)
	require.Contains(t, logs.String(), "callback_panic")
	require.NotContains(t, logs.String(), string(msg.payload))
}

func TestHandleFileProcessDelivery_DiagnosticsNeverIncludePayload(t *testing.T) {
	msg := &fakeProcessDeliveryMessage{payload: []byte(`{"id":"secret-id","type":"bad","source_key":"secret/source"}`)}
	var logs bytes.Buffer
	logger := slog.New(slog.NewTextHandler(&logs, nil))
	handleFileProcessDelivery(context.Background(), msg, &natsTemporalClientStub{calls: make(chan struct{}, 1)}, logger)
	require.NotContains(t, logs.String(), "secret-id")
	require.NotContains(t, logs.String(), "secret/source")
	require.NotContains(t, logs.String(), strings.TrimSpace(string(msg.payload)))
}

func TestDecodeProcessJobRejectsGenericEnvelope(t *testing.T) {
	_, err := decodeProcessJob([]byte(`{"id":"job","name":"process_uploaded_file","args":[],"kwargs":{}}`))
	require.Error(t, err)
}

func TestReconcileFileProcessConsumerMigratesLegacyInPlace(t *testing.T) {
	js := &fakeLegacyNatsJetStream{consumerInfo: &nats.ConsumerInfo{Config: nats.ConsumerConfig{
		Name: "file-processors-temporal", Durable: "file-processors-temporal", MaxDeliver: -1,
		AckPolicy: nats.AckExplicitPolicy, FilterSubject: fileProcessSubject,
	}}}
	stream, existing, err := reconcileFileProcessConsumer(js, fileProcessSubject, fileProcessConsumer)
	require.NoError(t, err)
	require.Equal(t, "FILE_EVENTS", stream)
	require.True(t, existing)
	require.Equal(t, 1, js.updateCount)
	require.Equal(t, fileProcessMaxDeliver, js.updatedConfigs[0].MaxDeliver)
	require.Equal(t, nats.AckExplicitPolicy, js.updatedConfigs[0].AckPolicy)
}

func TestReconcileFileProcessConsumerIsIdempotent(t *testing.T) {
	js := &fakeLegacyNatsJetStream{consumerInfo: &nats.ConsumerInfo{Config: nats.ConsumerConfig{MaxDeliver: fileProcessMaxDeliver}}}
	_, existing, err := reconcileFileProcessConsumer(js, fileProcessSubject, fileProcessConsumer)
	require.NoError(t, err)
	require.True(t, existing)
	require.Zero(t, js.updateCount)
}

func TestReconcileFileProcessConsumerConvergesAfterConflict(t *testing.T) {
	js := &fakeLegacyNatsJetStream{
		consumerInfo:     &nats.ConsumerInfo{Config: nats.ConsumerConfig{MaxDeliver: -1}},
		updateErrs:       []error{errors.New("concurrent update")},
		applyUpdateOnErr: true,
	}
	stream, existing, err := reconcileFileProcessConsumer(js, fileProcessSubject, fileProcessConsumer)
	require.NoError(t, err)
	require.Equal(t, "FILE_EVENTS", stream)
	require.True(t, existing)
	require.Equal(t, fileProcessMaxDeliver, js.consumerInfo.Config.MaxDeliver)
}

func TestStartNatsSubscriberBindsExistingBoundedConsumer(t *testing.T) {
	js := &fakeLegacyNatsJetStream{consumerInfo: &nats.ConsumerInfo{Config: nats.ConsumerConfig{MaxDeliver: fileProcessMaxDeliver}}}
	conn := &fakeLegacyNatsConnection{js: js, closed: make(chan struct{})}
	oldConnect := connectLegacyNats
	connectLegacyNats = func(_ string, _ ...nats.Option) (legacyNatsConnection, error) { return conn, nil }
	t.Cleanup(func() { connectLegacyNats = oldConnect })
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	require.NoError(t, startNatsSubscriber(ctx, &config.Config{Environment: "testing"}, nil, discardLogger()))
	require.Equal(t, fileProcessSubject, js.subject)
	require.Equal(t, fileProcessConsumer, js.queue)
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
}

func TestReconcileFileProcessConsumerErrorsFailClosed(t *testing.T) {
	t.Run("lookup error", func(t *testing.T) {
		js := &fakeLegacyNatsJetStream{consumerInfoErr: errors.New("lookup failed")}
		_, _, err := reconcileFileProcessConsumer(js, fileProcessSubject, fileProcessConsumer)
		require.Error(t, err)
	})
	t.Run("nil info", func(t *testing.T) {
		js := &fakeLegacyNatsJetStream{returnNilInfo: true}
		_, _, err := reconcileFileProcessConsumer(js, fileProcessSubject, fileProcessConsumer)
		require.Error(t, err)
	})
	t.Run("refetch error", func(t *testing.T) {
		js := &fakeLegacyNatsJetStream{
			consumerInfo: &nats.ConsumerInfo{Config: nats.ConsumerConfig{MaxDeliver: -1}},
			updateErrs:   []error{errors.New("update conflict")},
			lookupErrs:   []error{nil, errors.New("refetch failed")},
		}
		_, _, err := reconcileFileProcessConsumer(js, fileProcessSubject, fileProcessConsumer)
		require.Error(t, err)
	})
	t.Run("refetch nil info", func(t *testing.T) {
		js := &fakeLegacyNatsJetStream{
			consumerInfo:    &nats.ConsumerInfo{Config: nats.ConsumerConfig{MaxDeliver: -1}},
			updateErrs:      []error{errors.New("update conflict")},
			nilInfoOnLookup: 2,
		}
		_, _, err := reconcileFileProcessConsumer(js, fileProcessSubject, fileProcessConsumer)
		require.Error(t, err)
	})
	t.Run("bounded conflict", func(t *testing.T) {
		js := &fakeLegacyNatsJetStream{
			consumerInfo: &nats.ConsumerInfo{Config: nats.ConsumerConfig{MaxDeliver: -1}},
			updateErrs:   []error{errors.New("one"), errors.New("two"), errors.New("three")},
		}
		_, _, err := reconcileFileProcessConsumer(js, fileProcessSubject, fileProcessConsumer)
		require.Error(t, err)
	})
}

func TestReconcileFileProcessConsumerRequiresStream(t *testing.T) {
	js := &fakeLegacyNatsJetStream{streamErr: errors.New("stream lookup failed")}
	_, _, err := reconcileFileProcessConsumer(js, fileProcessSubject, fileProcessConsumer)
	require.Error(t, err)
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
	require.NoError(t, startNatsSubscriber(ctx, &config.Config{Environment: "production"}, temporal, discardLogger()))
	require.NotNil(t, js.handler)

	// Invalid payloads are rejected before Temporal is called.
	js.handler(&nats.Msg{Data: []byte("not-json")})

	// A Temporal failure takes the Nak path.
	temporal.executeErr = errors.New("workflow unavailable")
	js.handler(&nats.Msg{Data: []byte(`{"id":"failed-job","type":"image_resize","source_key":"input/a.png","dest_key":"output/a.png"}`)})

	// A successful workflow reaches the Ack path. These synthetic messages have
	// no reply subject, so NATS reports the expected best-effort ack error.
	temporal.executeErr = nil
	js.handler(&nats.Msg{Data: []byte(`{"id":"successful-job","type":"image_resize","source_key":"input/a.png","dest_key":"output/a.png"}`)})
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
			require.Error(t, startNatsSubscriber(context.Background(), &config.Config{Environment: "production"}, nil, discardLogger()))
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
		require.Error(t, startNatsSubscriber(ctx, &config.Config{Environment: "testing"}, nil, discardLogger()))
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
		require.Error(t, startNatsSubscriber(ctx, &config.Config{Environment: "testing"}, nil, discardLogger()))
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
