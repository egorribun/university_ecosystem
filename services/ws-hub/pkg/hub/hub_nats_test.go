package hub

// Coverage tests (testing session 9) for the NATS message handlers, the
// Run loop + broadcastMessage fan-out and Stop idempotency.
//
// The NATS handler closures (handleChat / handleNotifications /
// handleCacheInvalidation) are invoked DIRECTLY with synthetic *nats.Msg
// values — no NATS connection is needed. msg.Reply is left empty so the
// JetStream NakWithDelay branch is never reached (it would require a live
// connection).

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net"
	"os"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/ws-hub/pkg/config"
)

// recordingAuthClient records Invalidate calls; mutex-guarded for -race.
type recordingAuthClient struct {
	mu             sync.Mutex
	invalidated    [][2]string
	refreshAllowed bool
}

func (r *recordingAuthClient) CanJoinRoom(_ context.Context, _, _ string) bool { return true }

func (r *recordingAuthClient) Invalidate(userID, room string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.invalidated = append(r.invalidated, [2]string{userID, room})
}

func (r *recordingAuthClient) RefreshRoomAuthorization(
	_ context.Context,
	userID, room string,
) (bool, error) {
	r.Invalidate(userID, room)
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.refreshAllowed, nil
}

func (r *recordingAuthClient) calls() [][2]string {
	r.mu.Lock()
	defer r.mu.Unlock()
	out := make([][2]string, len(r.invalidated))
	copy(out, r.invalidated)
	return out
}

func newNatsTestHub(auth RoomAuthClient, secret string, broadcastCap int) *Hub {
	logger := slog.New(slog.NewTextHandler(os.Stdout, nil))
	cfg := &config.Config{
		MaxClients:          10,
		BroadcastBufferSize: broadcastCap,
		BroadcastWorkers:    1,
		ClientMsgRateLimit:  10,
		ClientMsgRateBurst:  10,
		InternalSecret:      secret,
	}
	h := trackTestHub(NewHub(nil, logger, auth, cfg, nil))
	h.subscribeCacheInvalidations = func(nats.MsgHandler, ...nats.SubOpt) (*nats.Subscription, error) {
		return nil, nil
	}
	return h
}

func recvBroadcast(t *testing.T, h *Hub) *Message {
	t.Helper()
	select {
	case msg := <-h.Broadcast:
		return msg
	case <-time.After(2 * time.Second):
		t.Fatal("expected a message on h.Broadcast")
		return nil
	}
}

// ---------------------------------------------------------------------------
// handleChat
// ---------------------------------------------------------------------------

func TestHandleChat_ValidMessageLandsOnBroadcast(t *testing.T) {
	h := newNatsTestHub(&mockAuthClient{allowed: true}, "", 10)
	handler := h.handleChat(context.Background())

	payload := []byte(`{"type":"new_message","room":"room-1","payload":{"text":"hi"}}`)
	handler(&nats.Msg{Subject: "chat.room-1", Data: payload})

	msg := recvBroadcast(t, h)
	assert.Equal(t, "new_message", msg.Type)
	assert.Equal(t, "room-1", msg.Room)
}

func TestHandleChat_MalformedJSONDropped(t *testing.T) {
	h := newNatsTestHub(&mockAuthClient{allowed: true}, "", 10)
	handler := h.handleChat(context.Background())

	handler(&nats.Msg{Subject: "chat.room-1", Data: []byte("{not-json")})

	select {
	case msg := <-h.Broadcast:
		t.Fatalf("expected no broadcast for malformed payload, got %+v", msg)
	default:
	}
}

func TestHandleChat_CancelledContextReturnsEarly(t *testing.T) {
	h := newNatsTestHub(&mockAuthClient{allowed: true}, "", 10)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	handler := h.handleChat(ctx)

	handler(&nats.Msg{Subject: "chat.room-1", Data: []byte(`{"type":"x"}`)})

	select {
	case msg := <-h.Broadcast:
		t.Fatalf("expected no broadcast after context cancel, got %+v", msg)
	default:
	}
}

func TestHandleChat_FullChannelDropsWithoutNak(t *testing.T) {
	h := newNatsTestHub(&mockAuthClient{allowed: true}, "", 1)
	handler := h.handleChat(context.Background())

	// Fill the capacity-1 channel, then deliver a second message.
	handler(&nats.Msg{Subject: "chat.a", Data: []byte(`{"type":"first","room":"a"}`)})
	handler(&nats.Msg{Subject: "chat.a", Data: []byte(`{"type":"second","room":"a"}`)})

	first := recvBroadcast(t, h)
	assert.Equal(t, "first", first.Type)
	select {
	case msg := <-h.Broadcast:
		t.Fatalf("second message should have been dropped, got %+v", msg)
	default:
	}
}

// ---------------------------------------------------------------------------
// handleNotifications
// ---------------------------------------------------------------------------

func TestHandleNotifications_OverridesType(t *testing.T) {
	h := newNatsTestHub(&mockAuthClient{allowed: true}, "", 10)
	handler := h.handleNotifications(context.Background())

	payload := []byte(`{"type":"whatever","to":"user-1","payload":{"title":"t"}}`)
	handler(&nats.Msg{Subject: "notifications.user-1", Data: payload})

	msg := recvBroadcast(t, h)
	assert.Equal(t, "notification", msg.Type)
	assert.Equal(t, "user-1", msg.To)
}

func TestHandleNotifications_MalformedDropped(t *testing.T) {
	h := newNatsTestHub(&mockAuthClient{allowed: true}, "", 10)
	handler := h.handleNotifications(context.Background())

	handler(&nats.Msg{Subject: "notifications.u", Data: []byte("not json")})

	select {
	case <-h.Broadcast:
		t.Fatal("expected malformed notification to be dropped")
	default:
	}
}

// ---------------------------------------------------------------------------
// handleCacheInvalidation — HMAC-signed internal events
// ---------------------------------------------------------------------------

type invalidationData struct {
	EvictRoom bool   `json:"evict_room,omitempty"`
	RoomID    string `json:"room_id"`
	Timestamp uint64 `json:"timestamp"`
	UserID    string `json:"user_id"`
}

type membershipRecordingAuthClient struct {
	mu           sync.Mutex
	memberships  map[[2]string]bool
	refreshErr   error
	refreshCalls int
}

func (r *membershipRecordingAuthClient) CanJoinRoom(_ context.Context, userID, roomID string) bool {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.memberships[[2]string{userID, roomID}]
}

func (r *membershipRecordingAuthClient) Invalidate(userID, roomID string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	_ = userID
	_ = roomID
}

func (r *membershipRecordingAuthClient) RefreshRoomAuthorization(
	_ context.Context,
	userID, roomID string,
) (bool, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.refreshCalls++
	return r.memberships[[2]string{userID, roomID}], r.refreshErr
}

func signedInvalidationPayload(t *testing.T, secret string, data invalidationData) []byte {
	t.Helper()
	dataBytes, err := json.Marshal(data)
	require.NoError(t, err)
	mac := hmac.New(sha256.New, []byte(secret))
	_, err = mac.Write(dataBytes)
	require.NoError(t, err)
	signature := hex.EncodeToString(mac.Sum(nil))

	full, err := json.Marshal(map[string]any{
		"data":      data,
		"signature": signature,
	})
	require.NoError(t, err)
	return full
}

func TestHandleCacheInvalidation_ValidSignature(t *testing.T) {
	const user = "11111111-1111-1111-1111-111111111111"
	const room = "22222222-2222-2222-2222-222222222222"
	auth := &recordingAuthClient{}
	h := newNatsTestHub(auth, "internal-secret", 10) // pragma: allowlist secret
	handler := h.handleCacheInvalidation(context.Background())

	payload := signedInvalidationPayload(t, "internal-secret",
		invalidationData{RoomID: room, Timestamp: 1234, UserID: user})
	handler(&nats.Msg{Subject: "cache.invalidate", Data: payload})

	calls := auth.calls()
	require.Len(t, calls, 1)
	assert.Equal(t, [2]string{user, room}, calls[0])
}

func TestHandleCacheInvalidation_WildcardUserInvalidation(t *testing.T) {
	oldAck := jetStreamAckFunc
	oldTerm := jetStreamTermFunc
	t.Cleanup(func() {
		jetStreamAckFunc = oldAck
		jetStreamTermFunc = oldTerm
	})
	ackCalls := 0
	termCalls := 0
	jetStreamAckFunc = func(*nats.Msg) error {
		ackCalls++
		return nil
	}
	jetStreamTermFunc = func(*nats.Msg) error {
		termCalls++
		return nil
	}

	const user = "11111111-1111-1111-1111-111111111111"
	auth := &recordingAuthClient{}
	h := newNatsTestHub(auth, "internal-secret", 10) // pragma: allowlist secret
	payload := signedInvalidationPayload(t, "internal-secret", invalidationData{
		Timestamp: 1234,
		UserID:    user,
	})
	h.handleCacheInvalidation(context.Background())(&nats.Msg{
		Subject: "cache.invalidate",
		Data:    payload,
	})

	assert.Equal(t, [][2]string{{user, ""}}, auth.calls())
	assert.Equal(t, 1, ackCalls, "a signed wildcard invalidation must be acknowledged")
	assert.Zero(t, termCalls, "a signed wildcard invalidation is not a poison event")
}

func TestHandleCacheInvalidation_InvalidIdentifiersAreTermed(t *testing.T) {
	const user = "11111111-1111-1111-1111-111111111111"
	const room = "22222222-2222-2222-2222-222222222222"
	cases := []struct {
		name string
		data invalidationData
	}{
		{
			name: "malformed user id",
			data: invalidationData{RoomID: room, Timestamp: 1234, UserID: "not-a-uuid"},
		},
		{
			name: "malformed room id",
			data: invalidationData{RoomID: "not-a-uuid", Timestamp: 1234, UserID: user},
		},
		{
			name: "room eviction requires a room id",
			data: invalidationData{EvictRoom: true, Timestamp: 1234, UserID: user},
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			oldAck := jetStreamAckFunc
			oldTerm := jetStreamTermFunc
			t.Cleanup(func() {
				jetStreamAckFunc = oldAck
				jetStreamTermFunc = oldTerm
			})
			ackCalls := 0
			termCalls := 0
			jetStreamAckFunc = func(*nats.Msg) error {
				ackCalls++
				return nil
			}
			jetStreamTermFunc = func(*nats.Msg) error {
				termCalls++
				return nil
			}

			auth := &recordingAuthClient{}
			h := newNatsTestHub(auth, "internal-secret", 10) // pragma: allowlist secret
			h.handleCacheInvalidation(context.Background())(&nats.Msg{
				Subject: "cache.invalidate",
				Data:    signedInvalidationPayload(t, "internal-secret", tc.data),
			})

			assert.Empty(t, auth.calls())
			assert.Zero(t, ackCalls)
			assert.Equal(t, 1, termCalls)
		})
	}
}

func TestHandleCacheInvalidation_ValidSignatureWithoutAuthClient(t *testing.T) {
	h := newNatsTestHub(nil, "internal-secret", 10) // pragma: allowlist secret
	h.handleCacheInvalidation(context.Background())(&nats.Msg{
		Subject: "cache.invalidate",
		Data: signedInvalidationPayload(t, "internal-secret", invalidationData{
			RoomID:    "22222222-2222-2222-2222-222222222222",
			Timestamp: 1234,
			UserID:    "11111111-1111-1111-1111-111111111111",
		}),
	})
}

func TestHandleCacheInvalidationAcceptsPythonEvictionSignature(t *testing.T) {
	auth := &recordingAuthClient{}
	h := newNatsTestHub(auth, "testsecret", 10)
	const payload = `{"data":{"evict_room":true,"room_id":"22222222-2222-2222-2222-222222222222","timestamp":1234,"user_id":"11111111-1111-1111-1111-111111111111"},"signature":"478e2845bae80bce3435d37b1087b0e32b32087db6c702a4ad2aaa58a6bdfdc1"}`

	h.handleCacheInvalidation(context.Background())(&nats.Msg{
		Subject: "cache.invalidate",
		Data:    []byte(payload),
	})

	assert.Equal(t, [][2]string{{"11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"}}, auth.calls())
}

func TestHandleCacheInvalidation_EvictsOnlyRemovedUsersRoom(t *testing.T) {
	serverConn, clientConn := newConnPair(t)
	_ = clientConn
	otherServerConn, otherClientConn := newConnPair(t)
	_ = otherClientConn

	const removedUser = "11111111-1111-1111-1111-111111111111"
	const room = "22222222-2222-2222-2222-222222222222"
	auth := &membershipRecordingAuthClient{memberships: map[[2]string]bool{{removedUser, room}: false}}
	h := newNatsTestHub(auth, "internal-secret", 10) // pragma: allowlist secret
	removed := newClientOn(h, serverConn, "removed-client", removedUser)
	other := newClientOn(h, otherServerConn, "other-client", "other-user")
	removed.JoinRoom(room)
	other.JoinRoom(room)

	payload := signedInvalidationPayload(t, "internal-secret", invalidationData{
		EvictRoom: true,
		RoomID:    room,
		Timestamp: 1234,
		UserID:    removedUser,
	})
	h.handleCacheInvalidation(context.Background())(&nats.Msg{
		Subject: "cache.invalidate",
		Data:    payload,
	})

	assert.False(t, removed.Rooms[room], "removed user's socket must leave the room")
	assert.True(t, other.Rooms[room], "other room members must stay connected")
	assert.NotContains(t, h.Rooms[room], removed)
	assert.Contains(t, h.Rooms[room], other)
	select {
	case frame := <-removed.Send:
		var notice map[string]string
		require.NoError(t, json.Unmarshal(frame, &notice))
		assert.Equal(t, "room_access_revoked", notice["code"])
	default:
		t.Fatal("removed socket should receive a room access revocation notice")
	}
}

func TestHandleCacheInvalidation_ReplayedEvictionKeepsReaddedMember(t *testing.T) {
	serverConn, clientConn := newConnPair(t)
	_ = clientConn
	const user = "11111111-1111-1111-1111-111111111111"
	const room = "22222222-2222-2222-2222-222222222222"
	auth := &membershipRecordingAuthClient{memberships: map[[2]string]bool{{user, room}: true}}
	h := newNatsTestHub(auth, "internal-secret", 10) // pragma: allowlist secret
	client := newClientOn(h, serverConn, "readded-client", user)
	client.JoinRoom(room)

	payload := signedInvalidationPayload(t, "internal-secret", invalidationData{
		EvictRoom: true,
		RoomID:    room,
		Timestamp: 1234,
		UserID:    user,
	})
	h.handleCacheInvalidation(context.Background())(&nats.Msg{
		Subject: "cache.invalidate",
		Data:    payload,
	})

	assert.True(t, client.Rooms[room], "a stale replay must not evict a user who was re-added")
}

func TestHandleCacheInvalidation_RefreshFailureNaksWithoutAck(t *testing.T) {
	oldAck := jetStreamAckFunc
	oldNak := jetStreamNakFunc
	t.Cleanup(func() {
		jetStreamAckFunc = oldAck
		jetStreamNakFunc = oldNak
	})
	ackCalls := 0
	nakCalls := 0
	jetStreamAckFunc = func(*nats.Msg) error {
		ackCalls++
		return nil
	}
	jetStreamNakFunc = func(*nats.Msg, time.Duration) error {
		nakCalls++
		return nil
	}

	const user = "11111111-1111-1111-1111-111111111111"
	const room = "22222222-2222-2222-2222-222222222222"
	serverConn, clientConn := newConnPair(t)
	_ = clientConn
	auth := &membershipRecordingAuthClient{
		memberships: map[[2]string]bool{{user, room}: true},
		refreshErr:  errors.New("redis invalidation unavailable"),
	}
	h := newNatsTestHub(auth, "internal-secret", 10) // pragma: allowlist secret
	client := newClientOn(h, serverConn, "unconfirmed-revocation", user)
	client.JoinRoom(room)
	require.True(t, h.AuthorizeRoomJoin(context.Background(), user, room))
	payload := signedInvalidationPayload(t, "internal-secret", invalidationData{
		EvictRoom: true,
		RoomID:    room,
		Timestamp: 1234,
		UserID:    user,
	})

	h.handleCacheInvalidation(context.Background())(&nats.Msg{
		Subject: "cache.invalidate",
		Data:    payload,
	})

	assert.Equal(t, 0, ackCalls, "an unconfirmed revocation must remain unacked")
	assert.Equal(t, 1, nakCalls, "an unconfirmed revocation must be retried")
	assert.False(t, client.Rooms[room], "an unconfirmed revocation must close existing room access")
	assert.False(t, h.AuthorizeRoomJoin(context.Background(), user, room), "pending revocation must block stale cached authorization")

	auth.mu.Lock()
	auth.refreshErr = nil
	auth.mu.Unlock()
	assert.True(t, h.AuthorizeRoomJoin(context.Background(), user, room), "a later join must re-check authority instead of remaining blocked if the NATS event expired")
	assert.False(t, h.isRoomRevocationPending(user, room))
	h.handleCacheInvalidation(context.Background())(&nats.Msg{
		Subject: "cache.invalidate",
		Data:    payload,
	})
	assert.Equal(t, 1, ackCalls, "a confirmed refresh should acknowledge the durable event")
	assert.Equal(t, 1, nakCalls, "the recovered retry should not NAK again")
	assert.True(t, h.AuthorizeRoomJoin(context.Background(), user, room), "a confirmed re-add should clear the temporary join gate")
}

func TestBroadcastRecipientSnapshotDoesNotDeliverAfterRoomEviction(t *testing.T) {
	serverConn, clientConn := newConnPair(t)
	_ = clientConn
	const user = "11111111-1111-1111-1111-111111111111"
	const room = "22222222-2222-2222-2222-222222222222"
	auth := &membershipRecordingAuthClient{memberships: map[[2]string]bool{{user, room}: false}}
	h := newNatsTestHub(auth, "internal-secret", 10) // pragma: allowlist secret
	client := newClientOn(h, serverConn, "removed-client", user)
	client.JoinRoom(room)
	msg := &Message{Type: "new_message", Room: room}
	recipients := h.collectRecipients(msg, nil)
	require.Len(t, recipients, 1, "the snapshot should contain the member before revocation")

	require.NoError(t, h.evictRoomMembership(context.Background(), user, room))
	h.deliverBroadcastRecipient(context.Background(), msg, []byte(`{"type":"new_message"}`), recipients[0])

	select {
	case frame := <-client.Send:
		var notice map[string]string
		require.NoError(t, json.Unmarshal(frame, &notice))
		assert.Equal(t, "room_access_revoked", notice["code"])
	default:
		t.Fatal("the revocation notice should be queued before checking for stale delivery")
	}
	select {
	case frame := <-client.Send:
		t.Fatalf("stale broadcast snapshot delivered after eviction: %s", frame)
	default:
	}
}

func TestReplayFlushQueuedFrameIsNotWrittenAfterRoomRevocation(t *testing.T) {
	serverConn, clientConn := newConnPair(t)
	const user = "11111111-1111-1111-1111-111111111111"
	const room = "22222222-2222-2222-2222-222222222222"
	auth := &membershipRecordingAuthClient{memberships: map[[2]string]bool{{user, room}: false}}
	h := newNatsTestHub(auth, "internal-secret", 10) // pragma: allowlist secret
	client := newClientOn(h, serverConn, "replay-revoked-client", user)
	client.Send = make(chan []byte, 1)
	client.JoinRoom(room)

	replayCtx, cancelReplay := context.WithCancel(client.ctx)
	state := &roomReplayState{
		ctx:    replayCtx,
		cancel: cancelReplay,
		buffered: map[uint64][]byte{
			1: []byte(`{"type":"new_message","room":"22222222-2222-2222-2222-222222222222","replayed":true,"payload":{"text":"private-1"}}`),
			2: []byte(`{"type":"new_message","room":"22222222-2222-2222-2222-222222222222","replayed":true,"payload":{"text":"private-2"}}`),
		},
	}
	client.replayMu.Lock()
	client.replays = map[string]*roomReplayState{room: state}
	client.replayMu.Unlock()

	flushDone := make(chan bool, 1)
	go func() { flushDone <- client.flushRoomReplay(room, state, 0) }()
	require.Eventually(t, func() bool { return len(client.Send) == 1 }, time.Second, time.Millisecond)

	require.NoError(t, h.evictRoomMembership(context.Background(), user, room))
	select {
	case completed := <-flushDone:
		assert.False(t, completed, "revocation must cancel the still-running replay flush")
	case <-time.After(time.Second):
		t.Fatal("replay flush did not stop after room revocation")
	}
	assert.False(t, client.isInRoom(room))

	writeDone := make(chan struct{})
	go func() {
		client.WritePump()
		close(writeDone)
	}()
	require.NoError(t, clientConn.SetReadDeadline(time.Now().Add(100*time.Millisecond)))
	_, frame, err := clientConn.ReadMessage()
	assert.Error(t, err, "queued private replay data must not reach the revoked socket")
	assert.NotContains(t, string(frame), "private-1")

	client.Disconnect(1000, "test complete")
	select {
	case <-writeDone:
	case <-time.After(time.Second):
		t.Fatal("write pump did not stop after the client disconnected")
	}
}

func TestRoomScopedErrorPayloadIsDroppedAfterRoomRevocation(t *testing.T) {
	serverConn, clientConn := newConnPair(t)
	const user = "11111111-1111-1111-1111-111111111111"
	const room = "22222222-2222-2222-2222-222222222222"
	auth := &membershipRecordingAuthClient{memberships: map[[2]string]bool{{user, room}: false}}
	h := newNatsTestHub(auth, "internal-secret", 10) // pragma: allowlist secret
	client := newClientOn(h, serverConn, "revoked-error-frame-client", user)
	client.JoinRoom(room)
	client.Send <- []byte(`{"type":"error","room":"22222222-2222-2222-2222-222222222222","code":"backend_error","detail":"private failure","payload":{"secret":"private-data"}}`)

	require.NoError(t, h.evictRoomMembership(context.Background(), user, room))
	writeDone := make(chan struct{})
	go func() {
		client.WritePump()
		close(writeDone)
	}()
	defer func() {
		client.cancel()
		select {
		case <-writeDone:
		case <-time.After(time.Second):
			t.Error("write pump did not stop after cleanup")
		}
	}()

	require.NoError(t, clientConn.SetReadDeadline(time.Now().Add(time.Second)))
	_, frame, err := clientConn.ReadMessage()
	require.NoError(t, err)
	assert.Contains(t, string(frame), "room_access_revoked", "the explicit access notice must remain deliverable")
	assert.NotContains(t, string(frame), "private-data", "room-scoped error payloads must be dropped after revocation")
}

type roomWriteOrder struct {
	mu     sync.Mutex
	events []string
}

func (o *roomWriteOrder) add(event string) {
	o.mu.Lock()
	defer o.mu.Unlock()
	o.events = append(o.events, event)
}

func (o *roomWriteOrder) snapshot() []string {
	o.mu.Lock()
	defer o.mu.Unlock()
	return append([]string(nil), o.events...)
}

type blockedRoomWriteSession struct {
	writeStarted chan struct{}
	allowWrite   chan struct{}
	releaseOnce  sync.Once
	order        *roomWriteOrder
}

func (s *blockedRoomWriteSession) ReadMessage() (int, []byte, error) { return 0, nil, io.EOF }
func (s *blockedRoomWriteSession) SetReadLimit(int64)                {}
func (s *blockedRoomWriteSession) SetReadDeadline(time.Time) error   { return nil }
func (s *blockedRoomWriteSession) SetWriteDeadline(time.Time) error  { return nil }
func (s *blockedRoomWriteSession) SetPongHandler(func(string) error) {}
func (s *blockedRoomWriteSession) Close() error                      { return nil }
func (s *blockedRoomWriteSession) RemoteAddr() net.Addr              { return &net.TCPAddr{} }
func (s *blockedRoomWriteSession) TransportType() string             { return "test" }

func (s *blockedRoomWriteSession) WriteMessage(_ int, data []byte) error {
	var frame struct {
		Type string `json:"type"`
	}
	if err := json.Unmarshal(data, &frame); err != nil || frame.Type == "error" {
		return nil
	}
	s.writeStarted <- struct{}{}
	<-s.allowWrite
	s.order.add("private_frame_written")
	return nil
}

func (s *blockedRoomWriteSession) release() {
	s.releaseOnce.Do(func() { close(s.allowWrite) })
}

type roomRevocationOrderingAuth struct {
	order *roomWriteOrder
}

func (a *roomRevocationOrderingAuth) CanJoinRoom(context.Context, string, string) bool { return true }
func (a *roomRevocationOrderingAuth) Invalidate(string, string)                        {}
func (a *roomRevocationOrderingAuth) RefreshRoomAuthorization(context.Context, string, string) (bool, error) {
	a.order.add("authorization_denied")
	return false, nil
}

func TestRoomRevocationSerializesInFlightPrivateWriteWithAuthorizationRefresh(t *testing.T) {
	const user = "11111111-1111-1111-1111-111111111111"
	const room = "22222222-2222-2222-2222-222222222222"
	order := &roomWriteOrder{}
	auth := &roomRevocationOrderingAuth{
		order: order,
	}
	h := newNatsTestHub(auth, "internal-secret", 10) // pragma: allowlist secret
	ctx, cancel := context.WithCancel(context.Background())
	session := &blockedRoomWriteSession{
		writeStarted: make(chan struct{}, 1),
		allowWrite:   make(chan struct{}),
		order:        order,
	}
	client := &Client{
		ID:     "in-flight-revocation-client",
		UserID: user,
		Rooms:  make(map[string]bool),
		Conn:   session,
		Send:   make(chan []byte, 1),
		Hub:    h,
		ctx:    ctx,
		cancel: cancel,
	}
	client.JoinRoom(room)
	client.Send <- []byte(`{"type":"new_message","room":"22222222-2222-2222-2222-222222222222","payload":{"text":"private"}}`)
	writeDone := make(chan struct{})
	go func() {
		client.WritePump()
		close(writeDone)
	}()
	defer func() {
		session.release()
		cancel()
		select {
		case <-writeDone:
		case <-time.After(time.Second):
			t.Error("write pump did not stop after cleanup")
		}
	}()

	select {
	case <-session.writeStarted:
	case <-time.After(time.Second):
		t.Fatal("write pump did not enter the blocked private write")
	}
	// The session is blocked inside WriteMessage. A failed TryLock proves that
	// WritePump still owns the exact user/room stripe needed by revocation.
	membershipLock := h.roomMembershipLock(user, room)
	if membershipLock.TryLock() {
		membershipLock.Unlock()
		t.Fatal("write pump released the membership stripe during a private socket write")
	}

	evictionStarted := make(chan struct{})
	evictionDone := make(chan error, 1)
	go func() {
		close(evictionStarted)
		evictionDone <- h.evictRoomMembership(context.Background(), user, room)
	}()
	<-evictionStarted

	session.release()
	select {
	case err := <-evictionDone:
		require.NoError(t, err)
	case <-time.After(time.Second):
		t.Fatal("room eviction did not finish after the private write released")
	}
	events := order.snapshot()
	require.Equal(t, []string{"private_frame_written", "authorization_denied"}, events,
		"the private write must linearize before the authoritative denial")
	assert.False(t, client.isInRoom(room), "confirmed revocation must remove local room membership")
}

func TestHandleCacheInvalidation_BadSignatureDropped(t *testing.T) {
	auth := &recordingAuthClient{}
	h := newNatsTestHub(auth, "internal-secret", 10) // pragma: allowlist secret
	handler := h.handleCacheInvalidation(context.Background())

	payload := signedInvalidationPayload(t, "WRONG-secret", invalidationData{
		RoomID:    "22222222-2222-2222-2222-222222222222",
		Timestamp: 1234,
		UserID:    "11111111-1111-1111-1111-111111111111",
	})
	handler(&nats.Msg{Subject: "cache.invalidate", Data: payload})

	assert.Empty(t, auth.calls())
}

func TestHandleCacheInvalidation_MalformedAndBadHexDropped(t *testing.T) {
	auth := &recordingAuthClient{}
	h := newNatsTestHub(auth, "internal-secret", 10) // pragma: allowlist secret
	handler := h.handleCacheInvalidation(context.Background())

	handler(&nats.Msg{Subject: "cache.invalidate", Data: []byte("{broken")})

	// Valid JSON but non-hex signature → hex decode error branch.
	data, err := json.Marshal(map[string]any{
		"data": invalidationData{
			RoomID: "22222222-2222-2222-2222-222222222222", Timestamp: 1,
			UserID: "11111111-1111-1111-1111-111111111111",
		},
		"signature": "zz-not-hex",
	})
	require.NoError(t, err)
	handler(&nats.Msg{Subject: "cache.invalidate", Data: data})

	assert.Empty(t, auth.calls())
}

// ---------------------------------------------------------------------------
// Run loop + broadcastMessage fan-out
// ---------------------------------------------------------------------------

func startHubRunLoop(t *testing.T, h *Hub) (context.CancelFunc, chan struct{}) {
	t.Helper()
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{})
	go func() {
		defer close(done)
		h.Run(ctx)
	}()
	return cancel, done
}

func registerLoopClient(t *testing.T, h *Hub, id string, sendCap int) *Client {
	t.Helper()
	client := &Client{
		ID:    id,
		Rooms: make(map[string]bool),
		Send:  make(chan []byte, sendCap),
		Hub:   h,
		ctx:   context.Background(),
	}
	select {
	case h.Register <- client:
	case <-time.After(2 * time.Second):
		t.Fatal("Run loop did not consume Register")
	}
	require.Eventually(t, func() bool {
		h.mu.RLock()
		defer h.mu.RUnlock()
		_, ok := h.Clients[id]
		return ok
	}, 2*time.Second, 10*time.Millisecond)
	return client
}

func recvSend(t *testing.T, c *Client) Message {
	t.Helper()
	select {
	case data := <-c.Send:
		var msg Message
		require.NoError(t, json.Unmarshal(data, &msg))
		return msg
	case <-time.After(2 * time.Second):
		t.Fatalf("client %s did not receive a message", c.ID)
		return Message{}
	}
}

func TestRunLoop_RoomDirectAndGlobalDelivery(t *testing.T) {
	h := newNatsTestHub(&mockAuthClient{allowed: true}, "", 10)
	cancel, done := startHubRunLoop(t, h)
	defer func() { cancel(); <-done }()

	alice := registerLoopClient(t, h, "alice", 8)
	bob := registerLoopClient(t, h, "bob", 8)

	// Join alice to a room directly under the documented lock hierarchy.
	h.mu.Lock()
	h.Rooms["room-1"] = map[*Client]bool{alice: true}
	h.mu.Unlock()
	alice.mu.Lock()
	alice.Rooms["room-1"] = true
	alice.mu.Unlock()

	// Room-scoped: only alice receives.
	h.Broadcast <- &Message{Type: "room-msg", Room: "room-1", Payload: []byte(`{}`)}
	got := recvSend(t, alice)
	assert.Equal(t, "room-msg", got.Type)

	// Direct: only bob receives.
	h.Broadcast <- &Message{Type: "direct-msg", To: "bob", Payload: []byte(`{}`)}
	got = recvSend(t, bob)
	assert.Equal(t, "direct-msg", got.Type)

	// Global: both receive.
	h.Broadcast <- &Message{Type: "global-msg", Payload: []byte(`{}`)}
	assert.Equal(t, "global-msg", recvSend(t, alice).Type)
	assert.Equal(t, "global-msg", recvSend(t, bob).Type)
}

func TestRunLoop_OversizedBroadcastDropped(t *testing.T) {
	h := newNatsTestHub(&mockAuthClient{allowed: true}, "", 10)
	cancel, done := startHubRunLoop(t, h)
	defer func() { cancel(); <-done }()

	alice := registerLoopClient(t, h, "alice", 8)

	// Oversized (>60 KB once marshalled) then a small follow-up: only the
	// follow-up must arrive, proving the oversized one was dropped.
	big := strings.Repeat("x", 61*1024)
	payload, err := json.Marshal(map[string]string{"blob": big})
	require.NoError(t, err)
	h.Broadcast <- &Message{Type: "oversized", Payload: payload}
	h.Broadcast <- &Message{Type: "small", Payload: []byte(`{}`)}

	got := recvSend(t, alice)
	assert.Equal(t, "small", got.Type)
}

func TestRunLoop_GlobalBroadcastEvictsFullClient(t *testing.T) {
	h := newNatsTestHub(&mockAuthClient{allowed: true}, "", 10)
	cancel, done := startHubRunLoop(t, h)
	defer func() { cancel(); <-done }()

	healthy := registerLoopClient(t, h, "healthy", 8)
	// Unbuffered Send channel with no reader → safeSend fails → evictOnFull.
	stuck := registerLoopClient(t, h, "stuck", 0)
	_ = stuck

	h.Broadcast <- &Message{Type: "global", Payload: []byte(`{}`)}
	assert.Equal(t, "global", recvSend(t, healthy).Type)

	require.Eventually(t, func() bool {
		h.mu.RLock()
		defer h.mu.RUnlock()
		_, ok := h.Clients["stuck"]
		return !ok
	}, 2*time.Second, 10*time.Millisecond, "stuck client should be evicted")
}

// ---------------------------------------------------------------------------
// Stop / HasJWKSCache
// ---------------------------------------------------------------------------

func TestStop_IsIdempotent(t *testing.T) {
	h := newNatsTestHub(&mockAuthClient{allowed: true}, "", 10)
	h.Stop()
	h.Stop() // second call must be a no-op (stopOnce)
}

func TestHasJWKSCache_FalseWithoutSetup(t *testing.T) {
	h := newNatsTestHub(&mockAuthClient{allowed: true}, "", 10)
	assert.False(t, h.HasJWKSCache())
}
