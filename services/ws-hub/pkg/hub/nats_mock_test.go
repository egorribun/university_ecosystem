package hub

import (
	"bufio"
	"context"
	"encoding/json"
	"io"
	"net"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/lestrrat-go/jwx/v2/jwk"
	"github.com/nats-io/nats.go"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

type mockNatsServer struct {
	listener net.Listener
	addr     string
	mu       sync.Mutex
	conns    []net.Conn
}

func newMockNatsServer(t *testing.T) *mockNatsServer {
	lc := net.ListenConfig{}
	l, err := lc.Listen(t.Context(), "tcp", "127.0.0.1:0")
	require.NoError(t, err)
	s := &mockNatsServer{
		listener: l,
		addr:     l.Addr().String(),
	}
	t.Cleanup(func() {
		if err := l.Close(); err != nil {
			t.Logf("mock NATS listener close failed: %v", err)
		}
		s.mu.Lock()
		for _, c := range s.conns {
			if err := c.Close(); err != nil {
				t.Logf("mock NATS conn close failed: %v", err)
			}
		}
		s.mu.Unlock()
	})
	go s.run()
	return s
}

func (s *mockNatsServer) Addr() string {
	return "nats://" + s.addr
}

func (s *mockNatsServer) run() {
	for {
		conn, err := s.listener.Accept()
		if err != nil {
			return
		}
		s.mu.Lock()
		s.conns = append(s.conns, conn)
		s.mu.Unlock()
		go s.handleConn(conn)
	}
}

func (s *mockNatsServer) handleConn(c net.Conn) {
	defer func() {
		if err := c.Close(); err != nil {
			return
		}
	}()
	info := `INFO {"server_id":"MOCK","version":"2.0.0","host":"127.0.0.1","port":4222,"auth_required":false,"max_payload":1048576}` + "\r\n"
	if _, err := c.Write([]byte(info)); err != nil {
		return
	}

	reader := bufio.NewReader(c)
	subscriptions := make(map[string][]string)
	for {
		line, err := reader.ReadString('\n')
		if err != nil {
			return
		}
		if !s.processLine(c, reader, line, subscriptions) {
			return
		}
	}
}

func (s *mockNatsServer) processLine(c net.Conn, reader *bufio.Reader, line string, subscriptions map[string][]string) bool {
	if strings.HasPrefix(line, "PING") {
		_, err := c.Write([]byte("PONG\r\n"))
		return err == nil
	}
	fields := strings.Fields(line)
	if len(fields) < 3 {
		return true
	}
	switch fields[0] {
	case "SUB":
		subject := fields[1]
		sid := fields[len(fields)-1]
		subscriptions[subject] = append(subscriptions[subject], sid)
		return true
	case "PUB":
		return s.handlePub(c, reader, fields, subscriptions)
	default:
		return true
	}
}

func (s *mockNatsServer) handlePub(c net.Conn, reader *bufio.Reader, fields []string, subscriptions map[string][]string) bool {
	size, parseErr := strconv.Atoi(fields[len(fields)-1])
	if parseErr != nil || size < 0 {
		return false
	}
	payloadWithCRLF := make([]byte, size+2)
	if _, readErr := io.ReadFull(reader, payloadWithCRLF); readErr != nil {
		return false
	}
	payload := payloadWithCRLF[:size]
	for _, sid := range subscriptions[fields[1]] {
		header := "MSG " + fields[1] + " " + sid + " " + strconv.Itoa(size) + "\r\n"
		frame := append([]byte(header), payload...)
		frame = append(frame, '\r', '\n')
		if _, writeErr := c.Write(frame); writeErr != nil {
			return false
		}
	}
	return true
}

func TestSubscribeToNATS_SuccessAndStop(t *testing.T) {
	server := newMockNatsServer(t)
	nc, err := nats.Connect(server.Addr())
	require.NoError(t, err)
	t.Cleanup(nc.Close)

	h := setupTestHub()
	h.Nats = nc
	// Core NATS remains an explicit operator-selected mode; replay-capable
	// JetStream startup no longer downgrades silently when prerequisites fail.
	h.enableJetStream = false

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	assert.NotPanics(t, func() {
		require.NoError(t, h.SubscribeToNATS(ctx))
	})

	assert.NotEmpty(t, h.subs)

	// Test Stop() draining subscriptions successfully
	assert.NotPanics(t, func() {
		h.Stop()
	})
}

func TestStop_DrainErrorLogging(t *testing.T) {
	server := newMockNatsServer(t)
	nc, err := nats.Connect(server.Addr())
	require.NoError(t, err)
	t.Cleanup(nc.Close)

	h := setupTestHub()
	h.Nats = nc

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	require.NoError(t, h.SubscribeToNATS(ctx))

	// Close NATS connection before Stop to cause Drain to return error
	nc.Close()

	assert.NotPanics(t, func() {
		h.Stop()
	})
}

func TestTryForceRefreshJWKS_Error(t *testing.T) {
	h := setupTestHub()
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	h.jwksCache = jwk.NewCache(ctx)
	h.jwksURL = "http://127.0.0.1:1/invalid" // definitely fails

	_lastJWKSForceRefreshUnix.Store(0) // reset cooldown
	assert.NotPanics(t, func() {
		h.tryForceRefreshJWKS(ctx)
	})
}

func TestClient_HandleMessage_NatsPublish(t *testing.T) {
	server := newMockNatsServer(t)
	nc, err := nats.Connect(server.Addr())
	require.NoError(t, err)
	t.Cleanup(nc.Close)

	h := setupTestHub()
	h.Nats = nc

	c := &Client{
		ID:     "c-nats",
		UserID: "u-nats",
		Hub:    h,
		ctx:    context.Background(),
		Send:   make(chan []byte, 10),
		Rooms:  map[string]bool{"room-1": true},
	}

	h.clientMsgRateLimit = 100
	h.clientMsgRateBurst = 100

	sub, err := nc.SubscribeSync("chat.room-1")
	require.NoError(t, err)
	require.NoError(t, nc.Flush())
	msg := Message{Type: "message", Room: "room-1", From: "spoofed", Payload: json.RawMessage(`{"text":"hello"}`)}
	data := []byte(`{"type":"message","room":"room-1","from":"spoofed","payload":{"text":"hello"}}`)
	assert.NotPanics(t, func() {
		c.handleMessage(msg, data)
	})
	published, err := sub.NextMsg(time.Second)
	require.NoError(t, err)
	var canonical Message
	require.NoError(t, json.Unmarshal(published.Data, &canonical))
	assert.Equal(t, "u-nats", canonical.From)
	assert.Equal(t, "room-1", canonical.Room)

	unauthorizedSub, err := nc.SubscribeSync("chat.room-2")
	require.NoError(t, err)
	require.NoError(t, nc.Flush())
	c.handleMessage(Message{Type: "message", Room: "room-2"}, []byte(`{"type":"message","room":"room-2"}`))
	_, err = unauthorizedSub.NextMsg(100 * time.Millisecond)
	assert.ErrorIs(t, err, nats.ErrTimeout)

	nc.Close()
	assert.NotPanics(t, func() {
		c.handleMessage(msg, data)
	})
}
