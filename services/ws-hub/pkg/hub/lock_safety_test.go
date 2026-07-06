package hub

import (
	"context"
	"fmt"
	"sync"
	"testing"
	"time"
)

// TestHub_LockSafety verifies that concurrent operations (registration, unregistration,
// joining, leaving, broadcasting, and map access) do not produce data races or deadlocks.
func TestHub_LockSafety(t *testing.T) {
	h := setupTestHub()
	// Override maxClients to ensure no client is rejected due to limit during test
	h.maxClients = 100

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Number of concurrent clients and operations
	const numClients = 10
	const numOperations = 50

	var wg sync.WaitGroup

	// Spin up clients and execute random concurrent operations to test lock acquisition order:
	// Hub.mu vs Client.mu
	clients := make([]*Client, numClients)
	for i := 0; i < numClients; i++ {
		clients[i] = &Client{
			ID:     fmt.Sprintf("client-%d", i),
			UserID: fmt.Sprintf("user-%d", i),
			Rooms:  make(map[string]bool),
			Send:   make(chan []byte, 100),
			Hub:    h,
			ctx:    ctx,
		}
		h.handleRegister(ctx, clients[i])
	}

	// Start the main run loop in the background to handle Broadcast messages
	go h.Run(ctx)

	// Channel to signal start to all goroutines at once to maximize concurrency
	startChan := make(chan struct{})

	// Goroutine 1: Join and leave rooms concurrently
	for i := 0; i < numClients; i++ {
		wg.Add(1)
		go func(c *Client) {
			defer wg.Done()
			<-startChan

			for j := 0; j < numOperations; j++ {
				room := fmt.Sprintf("room-%d", j%5)
				c.JoinRoom(room)
				c.LeaveRoom(room)
			}
		}(clients[i])
	}

	// Goroutine 2: Read active rooms and clients concurrently
	for i := 0; i < 5; i++ {
		wg.Add(1)
		go func(id int) {
			defer wg.Done()
			<-startChan

			for j := 0; j < numOperations; j++ {
				h.mu.RLock()
				_ = len(h.Clients)
				_ = len(h.Rooms)
				h.mu.RUnlock()
				time.Sleep(time.Microsecond)
			}
		}(i)
	}

	// Goroutine 3: Concurrent broadcast operations
	wg.Add(1)
	go func() {
		defer wg.Done()
		<-startChan

		for j := 0; j < numOperations; j++ {
			room := fmt.Sprintf("room-%d", j%5)
			msg := &Message{
				Type:    "chat",
				Room:    room,
				Payload: []byte(`{"text":"hello"}`),
			}
			h.Broadcast <- msg
			time.Sleep(time.Microsecond * 5)
		}
	}()

	// Start all concurrent goroutines
	close(startChan)

	// Wait with a timeout to detect deadlocks
	done := make(chan struct{})
	go func() {
		wg.Wait()
		close(done)
	}()

	select {
	case <-done:
		// Successful lock safety validation
	case <-time.After(5 * time.Second):
		t.Fatal("Deadlock detected! Lock safety test timed out after 5 seconds.")
	}

	// Clean up and unregister all remaining clients
	for i := 0; i < numClients; i++ {
		h.handleUnregister(ctx, clients[i])
	}
}
