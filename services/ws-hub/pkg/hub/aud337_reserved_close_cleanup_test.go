package hub

import (
	"context"
	"encoding/binary"
	"sync/atomic"
	"testing"
	"time"

	"github.com/gorilla/websocket"
	"github.com/stretchr/testify/require"
)

type aud337CloseTrackingSession struct {
	Session
	closeWrites atomic.Int32
	closeCode   atomic.Int32
	closeCalls  atomic.Int32
}

func (s *aud337CloseTrackingSession) WriteMessage(messageType int, data []byte) error {
	if messageType == websocket.CloseMessage {
		s.closeWrites.Add(1)
		if len(data) >= 2 {
			s.closeCode.Store(int32(binary.BigEndian.Uint16(data[:2])))
		}
	}
	return s.Session.WriteMessage(messageType, data)
}

func (s *aud337CloseTrackingSession) Close() error {
	s.closeCalls.Add(1)
	return s.Session.Close()
}

func TestAUD337StoppedEvictionReadCleanupClosesReservedTransportBeforeShutdownFanout(t *testing.T) {
	h, _ := newAUD337Hub()
	var tracked *aud337CloseTrackingSession
	client, conn, _ := startAUD337ClientWithBeforePumps(t, h, 8, false, func(client *Client, _ <-chan struct{}) {
		tracked = &aud337CloseTrackingSession{Session: client.Conn}
		client.Conn = tracked
	})

	if tracked == nil {
		t.Fatal("the close tracking session was not installed before pumps started")
		return
	}

	h.stopped.Store(true)
	h.scheduleClientEviction(client)
	require.ErrorIs(t, client.ctx.Err(), context.Canceled, "stopped eviction should cancel the client work")

	// The peer close drives ReadPump cleanup. Cleanup unregisters the client
	// before closeActiveClients can include it in its client snapshot.
	_ = conn.Close()
	require.Eventually(t, func() bool {
		h.mu.RLock()
		_, registered := h.Clients[client.ID]
		h.mu.RUnlock()
		return !registered && tracked.closeCalls.Load() == 1
	}, 2*time.Second, 10*time.Millisecond, "read cleanup must fulfill and close the reserved transport")
	require.EqualValues(t, 1, tracked.closeWrites.Load(), "cleanup must attempt the reserved control frame")
	require.EqualValues(t, websocket.CloseGoingAway, tracked.closeCode.Load())

	// Keep one unrelated client in the shutdown snapshot to prove the fanout
	// worker drains after the already-unregistered client is handled.
	drainSession := &recordingSession{}
	drainClosed := &closeNotifyingSession{recordingSession: drainSession, closed: make(chan struct{})}
	drainCtx, cancelDrain := context.WithCancel(context.Background())
	drainClient := &Client{
		ID:     "aud337-drain-client",
		UserID: "aud337-drain-user",
		Conn:   drainClosed,
		Rooms:  make(map[string]bool),
		Send:   make(chan []byte, 1),
		Hub:    h,
		ctx:    drainCtx,
		cancel: cancelDrain,
	}
	h.mu.Lock()
	h.Clients[drainClient.ID] = drainClient
	h.mu.Unlock()

	h.closeActiveClients(context.Background())
	select {
	case <-drainClosed.closed:
	default:
		t.Fatal("shutdown returned before its control-close worker drained")
	}
	require.Len(t, drainSession.writes, 1)
	require.Equal(t, websocket.CloseMessage, drainSession.writes[0].messageType)
	require.EqualValues(t, 1, tracked.closeCalls.Load(), "the omitted client must not be left open or closed twice")
	h.mu.RLock()
	require.Empty(t, h.Clients)
	h.mu.RUnlock()
}
