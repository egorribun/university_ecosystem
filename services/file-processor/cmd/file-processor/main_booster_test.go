package main

import (
	"bufio"
	"context"
	"net"
	"strings"
	"sync"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/file-processor/internal/config"
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
		go func(c net.Conn) {
			defer func() {
				_ = c.Close() //nolint:errcheck // best-effort close in mock server goroutine; t not in scope
			}()
			info := `INFO {"server_id":"MOCK","version":"2.0.0","host":"127.0.0.1","port":4222,"auth_required":false}` + "\r\n"
			if _, err := c.Write([]byte(info)); err != nil {
				return
			}

			reader := bufio.NewReader(c)
			for {
				line, err := reader.ReadString('\n')
				if err != nil {
					return
				}
				if strings.HasPrefix(line, "PING") {
					if _, err := c.Write([]byte("PONG\r\n")); err != nil {
						return
					}
				}
			}
		}(conn)
	}
}

// TestStartNatsSubscriber_JetStreamError verifies startNatsSubscriber connects successfully but handles
// JetStream initialization errors gracefully.
func TestStartNatsSubscriber_JetStreamError(t *testing.T) {
	server := newMockNatsServer(t)

	cfg := &config.Config{
		NatsURL:     server.Addr(),
		Environment: "testing",
	}

	assert.NotPanics(t, func() {
		startNatsSubscriber(context.Background(), cfg, nil, discardLogger())
	})
}
