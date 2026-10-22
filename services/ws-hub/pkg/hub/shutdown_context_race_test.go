package hub

import (
	"context"
	"errors"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/prometheus/client_golang/prometheus/testutil"
	"github.com/stretchr/testify/require"
)

type replayCancellationRegistrationGateContext struct {
	context.Context
	secondErrEntered chan struct{}
	allowSecondErr   <-chan struct{}
	errCalls         atomic.Int32
}

func (c *replayCancellationRegistrationGateContext) Err() error {
	err := c.Context.Err()
	if c.errCalls.Add(1) == 2 {
		close(c.secondErrEntered)
		<-c.allowSecondErr
	}
	return err
}

func TestRunRoomReplayCancellationRacesWorkerRegistration(t *testing.T) {
	h := setupTestHub()
	callerCtx, cancelCaller := context.WithCancel(context.Background())
	stateBaseCtx, cancelState := context.WithCancel(context.Background())
	allowSecondErr := make(chan struct{})
	var releaseOnce sync.Once
	releaseRegistration := func() {
		releaseOnce.Do(func() { close(allowSecondErr) })
	}
	stateCtx := &replayCancellationRegistrationGateContext{
		Context:          stateBaseCtx,
		secondErrEntered: make(chan struct{}),
		allowSecondErr:   allowSecondErr,
	}
	const room = "worker-cancel-registration-window"
	state := &roomReplayState{
		ctx:      stateCtx,
		cancel:   cancelState,
		buffered: make(map[uint64][]byte),
	}
	client := &Client{
		Hub:     h,
		Rooms:   make(map[string]bool),
		Send:    make(chan []byte, 1),
		ctx:     callerCtx,
		replays: map[string]*roomReplayState{room: state},
	}
	var pullCalls atomic.Int32
	h.js = &scriptedPullSubscription{pull: func(string, string, ...nats.SubOpt) (*nats.Subscription, error) {
		pullCalls.Add(1)
		return nil, errors.New("canceled replay must not open a pull subscription")
	}}
	baseline := testutil.ToFloat64(ActiveGoroutines)
	runDone := make(chan struct{})
	var cancelDone chan struct{}
	t.Cleanup(func() {
		releaseRegistration()
		state.cancelReplay()
		cancelCaller()
		select {
		case <-runDone:
		case <-time.After(time.Second):
			t.Error("runRoomReplay did not exit during cleanup")
		}
		if cancelDone != nil {
			select {
			case <-cancelDone:
			case <-time.After(time.Second):
				t.Error("state cancellation did not exit during cleanup")
			}
		}
		h.Stop()
	})

	go func() {
		client.runRoomReplay(callerCtx, room, 0, "", state)
		close(runDone)
	}()
	select {
	case <-stateCtx.secondErrEntered:
		// The state cancellation hook is checking the context while holding its
		// registration lock. Canceling here exercises the check/register window.
	case <-time.After(time.Second):
		t.Fatal("replay did not reach worker-cancellation registration")
	}
	cancelDone = make(chan struct{})
	go func() {
		state.cancelReplay()
		close(cancelDone)
	}()
	select {
	case <-stateBaseCtx.Done():
		// State cancellation happened while registration was paused.
	case <-time.After(time.Second):
		t.Fatal("state cancellation did not reach its state context")
	}
	releaseRegistration()
	select {
	case <-cancelDone:
	case <-time.After(time.Second):
		t.Fatal("state cancellation remained blocked after registration resumed")
	}
	select {
	case <-runDone:
	case <-time.After(time.Second):
		t.Fatal("canceled replay launch did not return")
	}

	require.ErrorIs(t, stateBaseCtx.Err(), context.Canceled)
	require.NoError(t, callerCtx.Err(), "canceling replay state must not cancel the caller context")
	workersDone := make(chan struct{})
	go func() {
		h.replayWG.Wait()
		close(workersDone)
	}()
	select {
	case <-workersDone:
	case <-time.After(time.Second):
		t.Fatal("canceled replay worker did not exit")
	}
	client.replayMu.Lock()
	remaining := client.replays[room]
	client.replayMu.Unlock()
	require.Nil(t, remaining, "canceled replay must remove its prepared barrier")
	require.Equal(t, baseline, testutil.ToFloat64(ActiveGoroutines), "canceled replay worker remained active")
	require.Zero(t, pullCalls.Load(), "a state canceled during hook registration must not open a pull subscription")
}

type replayStateWorkerRegistrationGateContext struct {
	context.Context
	errEntered chan struct{}
	allowErr   <-chan struct{}
	calls      atomic.Int32
}

func (c *replayStateWorkerRegistrationGateContext) Err() error {
	err := c.Context.Err()
	if c.calls.Add(1) == 1 {
		close(c.errEntered)
		<-c.allowErr
	}
	return err
}

func TestRoomReplayStateCancellationCancelsWorkerRegisteredDuringContextCheck(t *testing.T) {
	stateBaseCtx, cancelState := context.WithCancel(context.Background())
	allowErr := make(chan struct{})
	var releaseOnce sync.Once
	releaseErr := func() {
		releaseOnce.Do(func() { close(allowErr) })
	}
	stateCtx := &replayStateWorkerRegistrationGateContext{
		Context:    stateBaseCtx,
		errEntered: make(chan struct{}),
		allowErr:   allowErr,
	}
	callerCtx, cancelCaller := context.WithCancel(context.Background())
	workerCtx, cancelWorker := context.WithCancel(callerCtx)
	state := &roomReplayState{ctx: stateCtx, cancel: cancelState}
	var callbackOutsideLock atomic.Bool
	workerCancellation := context.CancelFunc(func() {
		if state.cancellationMu.TryLock() {
			callbackOutsideLock.Store(true)
			state.cancellationMu.Unlock()
		}
		cancelWorker()
	})
	registrationDone := make(chan struct{})
	cancelDone := make(chan struct{})
	var cancelStarted atomic.Bool
	var unregister func()

	t.Cleanup(func() {
		releaseErr()
		state.cancelReplay()
		registrationFinished := false
		select {
		case <-registrationDone:
			registrationFinished = true
		case <-time.After(time.Second):
			t.Error("worker cancellation registration did not exit during cleanup")
		}
		if cancelStarted.Load() {
			select {
			case <-cancelDone:
			case <-time.After(time.Second):
				t.Error("state cancellation did not exit during cleanup")
			}
		}
		if registrationFinished && unregister != nil {
			unregister()
		}
		cancelCaller()
		cancelWorker()
	})

	go func() {
		unregister = state.registerWorkerCancellation(workerCancellation)
		close(registrationDone)
	}()
	select {
	case <-stateCtx.errEntered:
		// Err captured the live state before registration can publish workerCancel.
	case <-time.After(time.Second):
		t.Fatal("worker registration did not reach its state-context check")
	}
	require.NoError(t, callerCtx.Err(), "caller context must remain independent from replay-state cancellation")

	cancelStarted.Store(true)
	go func() {
		state.cancelReplay()
		close(cancelDone)
	}()
	select {
	case <-stateBaseCtx.Done():
		// The state is canceled while registration still owns its cancellation lock.
	case <-time.After(time.Second):
		t.Fatal("state cancellation did not reach its context before registration resumed")
	}
	releaseErr()
	select {
	case <-registrationDone:
	case <-time.After(time.Second):
		t.Fatal("worker cancellation registration remained blocked after the state check resumed")
	}
	select {
	case <-cancelDone:
	case <-time.After(time.Second):
		t.Fatal("state cancellation did not finish after worker registration resumed")
	}
	select {
	case <-workerCtx.Done():
	case <-time.After(time.Second):
		t.Fatal("state cancellation lost the worker cancellation registered during its context check")
	}

	require.ErrorIs(t, stateBaseCtx.Err(), context.Canceled)
	require.ErrorIs(t, workerCtx.Err(), context.Canceled)
	require.NoError(t, callerCtx.Err(), "canceling replay state must not cancel the caller context")
	require.True(t, callbackOutsideLock.Load(), "worker cancellation callback must run after releasing the state mutex")
}

func TestHubStopWaitsForClientPumpReservationBeforeStart(t *testing.T) {
	h := setupTestHub()
	clientCtx, cancelClient := context.WithCancel(context.Background())
	session := newBlockingShutdownSession()
	client := &Client{
		ID:     "reserved-pumps-before-start",
		UserID: "reserved-pumps-user",
		Conn:   session,
		Rooms:  make(map[string]bool),
		Send:   make(chan []byte, 1),
		Hub:    h,
		ctx:    clientCtx,
		cancel: cancelClient,
	}
	runDone := make(chan struct{})
	stopDone := make(chan struct{})
	var reserved atomic.Bool
	var stopStarted atomic.Bool
	var startOnce sync.Once
	startReservedPumps := func() {
		if reserved.Load() {
			startOnce.Do(func() { h.startClientPumps(client, clientCtx) })
		}
	}
	t.Cleanup(func() {
		cancelClient()
		startReservedPumps()
		h.Stop()
		if stopStarted.Load() {
			select {
			case <-stopDone:
			case <-time.After(time.Second):
				t.Error("Hub.Stop did not exit during cleanup")
			}
		}
		select {
		case <-runDone:
		case <-time.After(time.Second):
			t.Error("Hub.Run did not exit during cleanup")
		}
	})

	go func() {
		h.Run(context.Background())
		close(runDone)
	}()
	require.Eventually(t, func() bool { return hubLifecycleContext(h) != nil }, time.Second, time.Millisecond)
	require.True(t, h.registerClient(client), "Run must receive the registration and reserve both pumps")
	reserved.Store(true)
	require.Eventually(t, func() bool {
		h.mu.RLock()
		defer h.mu.RUnlock()
		return h.Clients[client.ID] == client
	}, time.Second, time.Millisecond, "Run did not admit the reserved client")

	stopStarted.Store(true)
	go func() {
		h.Stop()
		close(stopDone)
	}()
	require.Eventually(t, func() bool { return h.stopped.Load() }, time.Second, time.Millisecond, "Hub.Stop did not seal lifecycle admission")
	select {
	case <-runDone:
	case <-time.After(time.Second):
		t.Fatal("Hub.Run did not exit after Stop sealed lifecycle admission")
	}
	select {
	case <-session.closed:
	case <-time.After(time.Second):
		t.Fatal("Stop did not close the active session before waiting for pumps")
	}
	select {
	case _, open := <-client.Send:
		require.False(t, open, "Stop must close the send queue before waiting for pumps")
	case <-time.After(time.Second):
		t.Fatal("Stop did not close the active send queue before waiting for pumps")
	}
	h.mu.RLock()
	_, stillActive := h.Clients[client.ID]
	h.mu.RUnlock()
	require.False(t, stillActive, "Stop must remove the active client before waiting for pumps")
	select {
	case <-stopDone:
		t.Fatal("Stop returned before the registration's reserved pumps started")
	default:
	}

	startReservedPumps()
	select {
	case <-session.readStarted:
	case <-time.After(time.Second):
		t.Fatal("the reserved read pump did not start after its admission was released")
	}
	select {
	case <-stopDone:
	case <-time.After(time.Second):
		t.Fatal("Stop did not finish after both reserved pumps exited")
	}
	require.ErrorIs(t, clientCtx.Err(), context.Canceled)
}

func TestRegisterWorkerCancellationRejectsCanceledState(t *testing.T) {
	stateCtx, cancelState := context.WithCancel(context.Background())
	cancelState()
	workerCtx, cancelWorker := context.WithCancel(context.Background())
	state := &roomReplayState{ctx: stateCtx}

	unregister := state.registerWorkerCancellation(cancelWorker)
	t.Cleanup(func() {
		unregister()
		cancelWorker()
	})

	require.ErrorIs(t, workerCtx.Err(), context.Canceled)
	state.cancellationMu.Lock()
	workerRegistered := state.workerCancel != nil
	serial := state.workerCancellationSerial
	state.cancellationMu.Unlock()
	require.False(t, workerRegistered, "canceled replay state must not retain a worker callback")
	require.Zero(t, serial, "rejected registration must not advance its cleanup serial")
}
