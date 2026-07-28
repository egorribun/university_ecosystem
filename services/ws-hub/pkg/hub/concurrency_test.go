package hub

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"sync"
	"testing"
	"time"

	"github.com/university-ecosystem/ws-hub/pkg/config"
	"go.opentelemetry.io/otel/trace"
)

func TestHub_MutexDeadlockConcurrency(t *testing.T) {
	// Create a new hub with mock authentication and small settings
	logger := slog.New(slog.NewTextHandler(os.Stdout, nil))
	cfg := &config.Config{
		MaxClients:          100,
		BroadcastBufferSize: 10,
		BroadcastWorkers:    2,
		ClientMsgRateLimit:  100,
		ClientMsgRateBurst:  100,
	}
	h := trackTestHub(NewHub(nil, logger, &mockAuthClient{allowed: true}, cfg, nil))

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	go h.Run(ctx)

	// We will concurrently spawn and delete clients, and push to broadcast
	const numGoroutines = 10
	const opsPerGoroutine = 20

	var wg sync.WaitGroup
	wg.Add(numGoroutines * 2)

	// Goroutines type A: register, join rooms, leave rooms, unregister
	for i := 0; i < numGoroutines; i++ {
		go func(id int) {
			defer wg.Done()
			for j := 0; j < opsPerGoroutine; j++ {
				clientID := fmt.Sprintf("user-%d-%d", id, j)
				c := &Client{
					ID:     clientID,
					UserID: clientID,
					Rooms:  make(map[string]bool),
					Send:   make(chan []byte, 1),
					Hub:    h,
					ctx:    ctx,
				}

				h.handleRegister(ctx, c)

				// Join some rooms
				room1 := fmt.Sprintf("room-%d", id)
				room2 := fmt.Sprintf("room-%d", (id+1)%numGoroutines)

				h.mu.Lock()
				if _, exists := h.Clients[c.ID]; exists {
					h.Rooms[room1] = map[*Client]bool{c: true}
					h.Rooms[room2] = map[*Client]bool{c: true}
					c.mu.Lock()
					c.Rooms[room1] = true
					c.Rooms[room2] = true
					c.mu.Unlock()
				}
				h.mu.Unlock()

				// Let other goroutines execute
				time.Sleep(1 * time.Millisecond)

				// Authorize and collect recipients
				h.collectRecipients(&Message{Room: room1}, trace.SpanFromContext(ctx))

				// Unregister
				h.handleUnregister(ctx, c)
			}
		}(i)
	}

	// Goroutines type B: simulate broadcast messages
	for i := 0; i < numGoroutines; i++ {
		go func(id int) {
			defer wg.Done()
			for j := 0; j < opsPerGoroutine; j++ {
				msg := &Message{
					Type:    "chat.message",
					Room:    fmt.Sprintf("room-%d", id),
					Payload: []byte(`{"text":"test"}`),
					From:    "sender",
				}
				select {
				case h.Broadcast <- msg:
				case <-time.After(5 * time.Millisecond):
					// Drop if broadcast is full to avoid blocking test indefinitely
				}
				time.Sleep(1 * time.Millisecond)
			}
		}(i)
	}

	// Wait with a timeout to detect deadlocks
	done := make(chan struct{})
	go func() {
		wg.Wait()
		close(done)
	}()

	select {
	case <-done:
		// Success
	case <-time.After(10 * time.Second):
		t.Fatal("Deadlock detected during concurrent Hub and Client lock operations")
	}
}
