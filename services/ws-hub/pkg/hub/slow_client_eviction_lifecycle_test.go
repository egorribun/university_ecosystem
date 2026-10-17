package hub

import (
	"context"
	"io"
	"net"
	"sync"
	"testing"
	"time"

	"github.com/prometheus/client_golang/prometheus/testutil"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

type blockingEvictionSession struct {
	readStarted chan struct{}
	closed      chan struct{}
	startOnce   sync.Once
	closeOnce   sync.Once
}

func newBlockingEvictionSession() *blockingEvictionSession {
	return &blockingEvictionSession{
		readStarted: make(chan struct{}),
		closed:      make(chan struct{}),
	}
}

func (s *blockingEvictionSession) ReadMessage() (int, []byte, error) {
	s.startOnce.Do(func() { close(s.readStarted) })
	<-s.closed
	return 0, nil, io.EOF
}

func (s *blockingEvictionSession) WriteMessage(int, []byte) error { return nil }

func (s *blockingEvictionSession) Close() error {
	s.closeOnce.Do(func() { close(s.closed) })
	return nil
}

func (s *blockingEvictionSession) RemoteAddr() net.Addr { return &net.TCPAddr{} }

func (s *blockingEvictionSession) TransportType() string { return "test" }

func (s *blockingEvictionSession) SetReadLimit(int64) {}

func (s *blockingEvictionSession) SetReadDeadline(time.Time) error { return nil }

func (s *blockingEvictionSession) SetWriteDeadline(time.Time) error { return nil }

func (s *blockingEvictionSession) SetPongHandler(func(string) error) {}

func TestSlowClientEvictionClosesTransportAndStopsReadPump(t *testing.T) {
	baseline := testutil.ToFloat64(ActiveConnections)
	h := setupTestHub()
	session := newBlockingEvictionSession()
	clientCtx, cancelClient := context.WithCancel(context.Background())
	client := &Client{
		ID:     "slow-client-eviction",
		UserID: "slow-client-user",
		Conn:   session,
		Hub:    h,
		Rooms:  make(map[string]bool),
		Send:   make(chan []byte),
		ctx:    clientCtx,
		cancel: cancelClient,
	}
	h.handleRegister(context.Background(), client)

	h.clientPumpWG.Add(1)
	readDone := make(chan struct{})
	go func() {
		defer h.clientPumpWG.Done()
		defer close(readDone)
		client.ReadPump(clientCtx)
	}()
	select {
	case <-session.readStarted:
	case <-time.After(time.Second):
		t.Fatal("read pump did not begin reading the evicted client")
	}

	t.Cleanup(func() {
		cancelClient()
		_ = session.Close()
		select {
		case <-readDone:
		case <-time.After(time.Second):
			t.Error("test cleanup could not stop the blocked read pump")
		}
		h.Stop()
		ActiveConnections.Set(baseline)
	})

	h.scheduleClientEviction(client)
	require.Eventually(t, func() bool {
		h.mu.RLock()
		defer h.mu.RUnlock()
		_, registered := h.Clients[client.ID]
		return !registered
	}, time.Second, time.Millisecond, "slow client should be removed from the hub")

	select {
	case <-session.closed:
	case <-time.After(50 * time.Millisecond):
		t.Fatal("slow-client eviction removed the client but left its transport open")
	}
	select {
	case <-readDone:
	case <-time.After(time.Second):
		t.Fatal("slow-client eviction left its read pump blocked")
	}
	assert.ErrorIs(t, clientCtx.Err(), context.Canceled)
}
