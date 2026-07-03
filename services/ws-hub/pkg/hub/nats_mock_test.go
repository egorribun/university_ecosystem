package hub

import (
	"bufio"
	"context"
	"net"
	"strings"
	"sync"
	"testing"

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
	l, err := net.Listen("tcp", "127.0.0.1:0")
	require.NoError(t, err)
	s := &mockNatsServer{
		listener: l,
		addr:     l.Addr().String(),
	}
	t.Cleanup(func() {
		_ = l.Close()
		s.mu.Lock()
		for _, c := range s.conns {
			_ = c.Close()
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
		go func(c net.Conn) {
			defer c.Close()
			info := `INFO {"server_id":"MOCK","version":"2.0.0","host":"127.0.0.1","port":4222,"auth_required":false}` + "\r\n"
			_, _ = c.Write([]byte(info))

			reader := bufio.NewReader(c)
			for {
				line, err := reader.ReadString('\n')
				if err != nil {
					return
				}
				if strings.HasPrefix(line, "PING") {
					_, _ = c.Write([]byte("PONG\r\n"))
				}
			}
		}(conn)
	}
}

func TestSubscribeToNATS_SuccessAndStop(t *testing.T) {
	server := newMockNatsServer(t)
	nc, err := nats.Connect(server.Addr())
	require.NoError(t, err)
	t.Cleanup(nc.Close)

	h := setupTestHub()
	h.Nats = nc

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	assert.NotPanics(t, func() {
		h.SubscribeToNATS(ctx)
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

	h.SubscribeToNATS(ctx)

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
	}

	h.clientMsgRateLimit = 100
	h.clientMsgRateBurst = 100

	msg := Message{Type: "message", Room: "room-1"}
	data := []byte(`{"text":"hello"}`)
	assert.NotPanics(t, func() {
		c.handleMessage(msg, data)
	})

	nc.Close()
	assert.NotPanics(t, func() {
		c.handleMessage(msg, data)
	})
}
