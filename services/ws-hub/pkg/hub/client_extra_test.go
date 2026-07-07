package hub

import (
	"context"
	"testing"
	"time"
)

func TestWritePump_WriteMessageError(t *testing.T) {
	h := setupTestHub()
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go h.Run(ctx)

	srv, cli := newConnPair(t)
	c := newClientOn(h, srv, "c-werr", "u-werr")

	// Close both ends to trigger write error
	if err := srv.Close(); err != nil {
		t.Log(err)
	}
	if err := cli.Close(); err != nil {
		t.Log(err)
	}

	// Put a message in Send
	c.Send <- []byte("msg")

	// Run WritePump, it should attempt to write and fail, returning immediately
	done := make(chan struct{})
	go func() {
		c.WritePump()
		close(done)
	}()

	select {
	case <-done:
	case <-time.After(2 * time.Second):
		t.Fatal("WritePump did not exit on WriteMessage error")
	}
}

func TestWritePump_CloseMessageError(t *testing.T) {
	h := setupTestHub()
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go h.Run(ctx)

	srv, cli := newConnPair(t)
	c := newClientOn(h, srv, "c-close-err", "u-close-err")

	// Close the connection to force close message write to fail
	if err := srv.Close(); err != nil {
		t.Log(err)
	}
	if err := cli.Close(); err != nil {
		t.Log(err)
	}

	safeClose(c.Send)

	done := make(chan struct{})
	go func() {
		c.WritePump()
		close(done)
	}()

	select {
	case <-done:
	case <-time.After(2 * time.Second):
		t.Fatal("WritePump did not exit on CloseMessage error")
	}
}

func TestClient_ReadPump_ErrorPaths(t *testing.T) {
	h := setupTestHub()
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go h.Run(ctx)

	srv, cli := newConnPair(t)
	c := newClientOn(h, srv, "c-read-err", "u-read-err")

	// Add to registered list so unregister works
	h.Register <- c

	// Close client connection immediately to trigger read error inside ReadPump
	if err := cli.Close(); err != nil {
		t.Log(err)
	}

	done := make(chan struct{})
	go func() {
		c.ReadPump()
		close(done)
	}()

	select {
	case <-done:
	case <-time.After(2 * time.Second):
		t.Fatal("ReadPump did not exit on ReadMessage error")
	}
}
