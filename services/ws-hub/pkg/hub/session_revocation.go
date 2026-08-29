package hub

import (
	"context"
	"fmt"
	"net"
	"sync"
	"time"

	"github.com/google/uuid"
	goredis "github.com/redis/go-redis/v9"
	"github.com/redis/go-redis/v9/maintnotifications"
)

const (
	// sessionRevocationsChannel is the backend's canonical durable-store event.
	// The backend writes revoked:jti before publishing this message.
	sessionRevocationsChannel = "session:revocations"
	// sessionActionRevocationTimeout bounds the security-store lookup before an
	// already-upgraded socket may dispatch a user action. A timeout rejects the
	// action rather than allowing a stale session through.
	sessionActionRevocationTimeout = 250 * time.Millisecond
	// defaultSessionRevocationSubscribeTimeout bounds the phase before a
	// concrete Pub/Sub object can be retained. Once the object exists, Stop
	// owns an explicit close function so an unacknowledged Receive cannot
	// outlive it.
	defaultSessionRevocationSubscribeTimeout = 5 * time.Second
)

var closeSessionRevocationPubSubFunc = func(pubsub *goredis.PubSub) error {
	return pubsub.Close()
}

// sessionRevocationSubscriber is an isolated client for the long-lived
// listener. The durable action-check client must remain available when a
// listener bootstrap stalls. go-redis can block in connection initialization
// when its read timeout is disabled, so the dialer retains each raw socket for
// lifecycle cancellation before a *PubSub object has been returned.
type sessionRevocationSubscriber struct {
	client *goredis.Client

	mu          sync.Mutex
	connections map[net.Conn]struct{}
	closed      bool
	closeOnce   sync.Once
	closeErr    error
}

func newSessionRevocationSubscriber(source *goredis.Client) *sessionRevocationSubscriber {
	options := *source.Options()
	// The listener has one responsibility: receive the canonical revocation
	// channel. It must not inherit the action client's cache or maintenance
	// notification manager, which would add unrelated background work and can
	// share push-handler state with the source client.
	options.ClientSideCache = nil
	options.ClientSideCacheConfig = nil
	options.PushNotificationProcessor = nil
	options.MaintNotificationsConfig = &maintnotifications.Config{
		Mode: maintnotifications.ModeDisabled,
	}
	dial := options.Dialer
	if dial == nil {
		dial = goredis.NewDialer(&options)
	}
	subscriber := &sessionRevocationSubscriber{
		connections: make(map[net.Conn]struct{}),
	}
	options.Dialer = func(ctx context.Context, network, address string) (net.Conn, error) {
		connection, err := dial(ctx, network, address)
		if err != nil {
			return nil, err
		}
		if !subscriber.trackConnection(connection) {
			_ = connection.Close()
			return nil, net.ErrClosed
		}
		return connection, nil
	}
	subscriber.client = goredis.NewClient(&options)
	return subscriber
}

func (s *sessionRevocationSubscriber) trackConnection(connection net.Conn) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.closed {
		return false
	}
	s.connections[connection] = struct{}{}
	return true
}

func (s *sessionRevocationSubscriber) close() error {
	s.closeOnce.Do(func() {
		s.mu.Lock()
		s.closed = true
		connections := make([]net.Conn, 0, len(s.connections))
		for connection := range s.connections {
			connections = append(connections, connection)
		}
		clear(s.connections)
		s.mu.Unlock()

		// Close raw connections before the client pools. A connection still in
		// go-redis initConn has not reached the Pub/Sub pool's active map yet.
		for _, connection := range connections {
			_ = connection.Close()
		}
		s.closeErr = s.client.Close()
	})
	return s.closeErr
}

// StartSessionRevocationListener consumes canonical session revocation events
// from the dedicated noeviction Redis. It waits for the subscription
// acknowledgement before returning so bootstrap cannot silently start without
// the live-disconnect path. Per-action tombstone checks remain mandatory: Redis
// Pub/Sub is at-most-once and a missed notification must never authorize work.
func (h *Hub) StartSessionRevocationListener(ctx context.Context) error {
	if h == nil {
		return fmt.Errorf("cannot start session revocation listener on nil hub")
	}
	if h.revocationRedisClient == nil {
		return fmt.Errorf("revocation Redis is required for session listener")
	}
	if h.stopped.Load() {
		return fmt.Errorf("cannot start session revocation listener after hub shutdown")
	}

	listenerCtx, cancel := context.WithCancel(ctx)
	subscriber := newSessionRevocationSubscriber(h.revocationRedisClient)
	closeSubscriber := func(logCtx context.Context) {
		if closeErr := subscriber.close(); closeErr != nil && h.Logger != nil {
			h.Logger.WarnContext(logCtx, "Failed to close session revocation subscriber", "err", closeErr)
		}
	}
	h.lifecycleMu.Lock()
	if h.stopped.Load() {
		h.lifecycleMu.Unlock()
		cancel()
		return fmt.Errorf("cannot start session revocation listener after hub shutdown")
	}
	h.sessionRevocationGeneration++
	generation := h.sessionRevocationGeneration
	previousCancel := h.sessionRevocationCancel
	// Add while lifecycleMu is held before even attempting the network
	// subscription. Stop sets stopped under the same mutex, so it can cancel and
	// join a listener that is stalled before Redis sends its acknowledgement.
	h.sessionRevocationWG.Add(1)
	h.sessionRevocationCancel = func() {
		cancel()
		closeSubscriber(context.Background())
	}
	h.lifecycleMu.Unlock()
	if previousCancel != nil {
		previousCancel()
	}

	startupTimeout := h.sessionRevocationSubscribeTimeout
	if startupTimeout <= 0 {
		startupTimeout = defaultSessionRevocationSubscribeTimeout
	}
	// Client.Subscribe can block in go-redis connection initialization before
	// returning a PubSub handle. context.AfterFunc closes the captured raw socket
	// on timeout/cancellation, making the bound enforceable even when the source
	// client deliberately has ReadTimeout disabled for idle Pub/Sub.
	startupCtx, startupCancel := context.WithTimeout(listenerCtx, startupTimeout)
	stopStartupAbort := context.AfterFunc(startupCtx, func() {
		closeSubscriber(context.Background())
	})
	pubsub := subscriber.client.Subscribe(startupCtx, sessionRevocationsChannel)
	startupErr := startupCtx.Err()
	stopStartupAbort()
	startupCancel()

	var closeOnce sync.Once
	closePubSub := func(logCtx context.Context) {
		closeOnce.Do(func() {
			if closeErr := closeSessionRevocationPubSubFunc(pubsub); closeErr != nil && h.Logger != nil {
				h.Logger.WarnContext(logCtx, "Failed to close session revocation subscription", "err", closeErr)
			}
		})
	}
	finish := func() {
		cancel()
		closeSubscriber(listenerCtx)
		closePubSub(listenerCtx)
		h.lifecycleMu.Lock()
		if h.sessionRevocationGeneration == generation {
			h.sessionRevocationCancel = nil
		}
		h.lifecycleMu.Unlock()
		h.sessionRevocationWG.Done()
	}

	h.lifecycleMu.Lock()
	if h.stopped.Load() || h.sessionRevocationGeneration != generation || startupErr != nil || listenerCtx.Err() != nil {
		h.lifecycleMu.Unlock()
		finish()
		if h.stopped.Load() {
			return fmt.Errorf("cannot start session revocation listener after hub shutdown")
		}
		if startupErr != nil {
			return fmt.Errorf("subscribe to session revocations: %w", startupErr)
		}
		return fmt.Errorf("session revocation listener startup was cancelled")
	}
	// Replace the provisional bootstrap stop function with a concrete Pub/Sub
	// close. PubSub.Receive only observes a context deadline captured when it
	// starts; closing the socket is therefore required to wake an already-blocked
	// read.
	h.sessionRevocationCancel = func() {
		cancel()
		closeSubscriber(context.Background())
		closePubSub(context.Background())
	}
	h.lifecycleMu.Unlock()

	if _, err := pubsub.Receive(listenerCtx); err != nil {
		finish()
		return fmt.Errorf("subscribe to session revocations: %w", err)
	}

	startTrackedGoroutine(func() {
		h.consumeSessionRevocations(listenerCtx, pubsub)
	}, finish)
	return nil
}

func (h *Hub) consumeSessionRevocations(ctx context.Context, pubsub *goredis.PubSub) {
	h.consumeSessionRevocationMessages(ctx, pubsub.Channel())
}

func (h *Hub) consumeSessionRevocationMessages(ctx context.Context, messages <-chan *goredis.Message) {
	for {
		select {
		case <-ctx.Done():
			return
		case message, ok := <-messages:
			if !ok {
				if h.Logger != nil && ctx.Err() == nil {
					h.Logger.ErrorContext(ctx, "Session revocation listener stopped; action checks remain fail-closed",
						"event", "session_revocation_listener_stopped")
				}
				return
			}
			if message == nil || !isValidSessionRevocationJTI(message.Payload) {
				if h.Logger != nil {
					h.Logger.WarnContext(ctx, "Ignored malformed session revocation event",
						"event", "session_revocation_event_invalid")
				}
				continue
			}
			h.DisconnectSession(message.Payload, 4401, "Session revoked")
		}
	}
}

func isValidSessionRevocationJTI(jti string) bool {
	// Redis keys and Pub/Sub payloads are byte-addressed. uuid.Validate accepts
	// multiple parseable spellings, but a non-canonical spelling would not match
	// the canonical lower-case producer when a session is revoked.
	parsed, err := uuid.Parse(jti)
	return err == nil && parsed.String() == jti
}
