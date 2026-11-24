package hub

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/university-ecosystem/ws-hub/pkg/config"
	"golang.org/x/time/rate"
)

const r23Room = "11111111-1111-4111-8111-111111111111"

var r23NonceA = strings.Repeat("a", 32)
var r23NonceB = strings.Repeat("b", 32)

type r23Auth struct{}

func (*r23Auth) CanJoinRoom(_ context.Context, user, _ string) bool { return user != "denied" }
func (*r23Auth) Invalidate(string, string)                          {}

func r23Hub(t *testing.T) (*Hub, context.Context, context.CancelFunc) {
	t.Helper()
	ctx, cancel := context.WithCancel(context.Background())
	h, err := NewHub(nil, slog.New(slog.NewTextHandler(io.Discard, nil)), &r23Auth{}, &config.Config{MaxClients: 10, BroadcastWorkers: 1}, nil)
	if err != nil {
		t.Fatal("hub setup failed")
	}
	h.sessionRevocationCheck = func(context.Context, string) error { return nil }
	t.Cleanup(func() { cancel(); h.Stop() })
	return h, ctx, cancel
}
func r23Client(h *Hub, ctx context.Context, cancel context.CancelFunc, user string) *Client {
	return &Client{ID: user, UserID: user, SessionJTI: "synthetic", SessionExpiresAt: time.Now().Add(time.Minute), Hub: h, Rooms: map[string]bool{}, Send: make(chan []byte, 8), ctx: ctx, cancel: cancel}
}
func r23Dispatch(c *Client, raw string) error {
	var msg Message
	if err := json.Unmarshal([]byte(raw), &msg); err != nil {
		return err
	}
	if !isAllowedMessageType(msg.Type) {
		return errors.New("invalid test frame")
	}
	mergeTopLevelJoinReplay(&msg, []byte(raw))
	stripClientReplayMetadata(&msg)
	msg.From = c.UserID
	return c.authorizeAndHandleIncomingMessage(c.ctx, msg, []byte(raw))
}
func r23Next(t *testing.T, c *Client) map[string]any {
	t.Helper()
	select {
	case b := <-c.Send:
		var out map[string]any
		if json.Unmarshal(b, &out) != nil {
			t.Fatal("invalid synthetic response")
		}
		return out
	default:
		t.Fatal("missing expected frame")
		return nil
	}
}
func r23Empty(t *testing.T, c *Client) {
	t.Helper()
	select {
	case <-c.Send:
		t.Fatal("unexpected frame")
	default:
	}
}
func r23JoinRaw(nonce string) string {
	return fmt.Sprintf(`{"type":"join","room":%q,"payload":{"admission_nonce":%q}}`, r23Room, nonce)
}

func TestR23LegacyHeartbeatAndJoinRemainUnchanged(t *testing.T) {
	h, ctx, cancel := r23Hub(t)
	c := r23Client(h, ctx, cancel, "one")
	ping := fmt.Sprintf(`{"type":"heartbeat_ping","nonce":%q}`, r23NonceA)
	if err := r23Dispatch(c, ping); err != nil {
		t.Fatal("legacy ping failed")
	}
	expected := fmt.Sprintf(`{"type":"heartbeat_pong","nonce":%q}`, r23NonceA)
	select {
	case raw := <-c.Send:
		if string(raw) != expected {
			t.Fatal("legacy pong changed")
		}
	default:
		t.Fatal("legacy pong missing")
	}
	if err := r23Dispatch(c, fmt.Sprintf(`{"type":"join","room":%q}`, r23Room)); err != nil || !c.isInRoom(r23Room) {
		t.Fatal("legacy join changed")
	}
	r23Empty(t, c)
}

func TestR23FreshOptInAcknowledgesOnlyRequester(t *testing.T) {
	h, ctx, cancel := r23Hub(t)
	first := r23Client(h, ctx, cancel, "first")
	second := r23Client(h, ctx, cancel, "second")
	second.UserID = first.UserID
	if err := r23Dispatch(second, fmt.Sprintf(`{"type":"join","room":%q}`, r23Room)); err != nil || !second.isInRoom(r23Room) {
		t.Fatal("legacy join failed")
	}
	r23Empty(t, second)
	if err := r23Dispatch(first, r23JoinRaw(r23NonceB)); err != nil || !first.isInRoom(r23Room) {
		t.Fatal("opt-in join failed")
	}
	frame := r23Next(t, first)
	if frame["type"] != "room_admitted" || frame["room"] != r23Room || frame["nonce"] != r23NonceB || len(frame) != 3 {
		t.Fatal("admission frame mismatch")
	}
	r23Empty(t, second)
	if len(h.Broadcast) != 0 || h.Nats != nil {
		t.Fatal("ack escaped local connection")
	}
}

func TestR23InvalidOptInsLeaveLegacyJoinBehavior(t *testing.T) {
	h, ctx, cancel := r23Hub(t)
	c := r23Client(h, ctx, cancel, "one")
	for _, raw := range []string{
		fmt.Sprintf(`{"type":"join","room":%q}`, r23Room),
		fmt.Sprintf(`{"type":"join","room":%q,"payload":{"admission_nonce":"bad"}}`, r23Room),
		fmt.Sprintf(`{"type":"join","room":%q,"payload":{"admission_nonce":42}}`, r23Room),
		fmt.Sprintf(`{"type":"join","room":%q,"payload":{"admission_nonce":%q,"unknown":true}}`, r23Room, r23NonceB),
		fmt.Sprintf(`{"type":"join","room":%q,"payload":{"admission_nonce":%q,"admission_nonce":%q}}`, r23Room, r23NonceA, r23NonceB),
	} {
		if err := r23Dispatch(c, raw); err != nil || !c.isInRoom(r23Room) {
			t.Fatal("legacy join changed")
		}
		r23Empty(t, c)
	}
}

func TestR23DenialAndRevocationNeverAcknowledgeAdmission(t *testing.T) {
	h, ctx, cancel := r23Hub(t)
	denied := r23Client(h, ctx, cancel, "denied")
	if err := r23Dispatch(denied, r23JoinRaw(r23NonceB)); err != nil {
		t.Fatal("unexpected session error")
	}
	if denied.isInRoom(r23Room) {
		t.Fatal("denied user joined")
	}
	r23Empty(t, denied)
	revoked := r23Client(h, ctx, cancel, "revoked")
	h.sessionRevocationCheck = func(context.Context, string) error { return errors.New("synthetic denial") }
	if err := r23Dispatch(revoked, r23JoinRaw(r23NonceB)); err == nil {
		t.Fatal("revoked join accepted")
	}
	r23Empty(t, revoked)
}

func TestR23FullQueueDoesNotChangeMembership(t *testing.T) {
	h, ctx, cancel := r23Hub(t)
	c := r23Client(h, ctx, cancel, "one")
	c.Send = make(chan []byte, 1)
	c.Send <- []byte(`{"type":"synthetic"}`)
	if err := r23Dispatch(c, r23JoinRaw(r23NonceB)); err != nil || !c.isInRoom(r23Room) {
		t.Fatal("join changed")
	}
	<-c.Send
	r23Empty(t, c)
}

func TestR23MergePreservesMalformedOptionalNonceWithoutChangingReplay(t *testing.T) {
	raw := fmt.Sprintf(`{"type":"join","room":%q,"resume_token":"synthetic","payload":{"admission_nonce":42}}`, r23Room)
	var msg Message
	if json.Unmarshal([]byte(raw), &msg) != nil {
		t.Fatal("decode failed")
	}
	mergeTopLevelJoinReplay(&msg, []byte(raw))
	var payload joinPayload
	if json.Unmarshal(msg.Payload, &payload) != nil || payload.ResumeToken != "synthetic" {
		t.Fatal("replay changed")
	}
	if len(payload.AdmissionNonce) != 0 {
		t.Fatal("malformed optional nonce was retained")
	}
	if admissionNonce(msg.Payload) != "" {
		t.Fatal("malformed nonce accepted")
	}
}

func TestR23QueuedOldAckRequiresClientAttemptFiltering(t *testing.T) {
	h, ctx, cancel := r23Hub(t)
	c := r23Client(h, ctx, cancel, "one")
	if r23Dispatch(c, r23JoinRaw(r23NonceA)) != nil {
		t.Fatal("first join failed")
	}
	if r23Dispatch(c, fmt.Sprintf(`{"type":"leave","room":%q}`, r23Room)) != nil {
		t.Fatal("leave failed")
	}
	if r23Dispatch(c, r23JoinRaw(r23NonceB)) != nil {
		t.Fatal("second join failed")
	}
	old, newer := r23Next(t, c), r23Next(t, c)
	if old["nonce"] != r23NonceA || newer["nonce"] != r23NonceB {
		t.Fatal("attempt correlation lost")
	}
	// Current membership can allow a previously queued ACK to be written after
	// rejoin, so clients must filter by current socket and current attempt nonce.
}

type r23BlockingJetStream struct {
	nats.JetStreamContext
	started, release chan struct{}
}

func (j *r23BlockingJetStream) PullSubscribe(string, string, ...nats.SubOpt) (*nats.Subscription, error) {
	close(j.started)
	<-j.release
	return nil, errors.New("synthetic offline stop")
}
func TestR23ValidResumeAcksAfterReplayBarrierInstalled(t *testing.T) {
	h, ctx, cancel := r23Hub(t)
	c := r23Client(h, ctx, cancel, "one")
	var secret [32]byte
	if _, err := rand.Read(secret[:]); err != nil {
		t.Fatal("random setup failed")
	}
	h.internalSecret = hex.EncodeToString(secret[:])
	h.chatStreamIncarnation = "synthetic-incarnation"
	h.streamChat = "CHAT_EVENTS"
	h.chatReplayAvailable.Store(true)
	js := &r23BlockingJetStream{started: make(chan struct{}), release: make(chan struct{})}
	h.js = js
	defer func() { close(js.release); cancel() }()
	token, err := h.issueResumeToken(c.UserID, r23Room, h.streamChat, 7)
	if err != nil {
		t.Fatal("resume setup failed")
	}
	raw := fmt.Sprintf(`{"type":"join","room":%q,"resume_token":%q,"payload":{"admission_nonce":%q}}`, r23Room, token, r23NonceB)
	if err := r23Dispatch(c, raw); err != nil {
		t.Fatal("resume failed")
	}
	select {
	case <-js.started:
	case <-time.After(time.Second):
		t.Fatal("replay did not start")
	}
	c.replayMu.Lock()
	state := c.replays[r23Room]
	c.replayMu.Unlock()
	if state == nil || !c.isInRoom(r23Room) {
		t.Fatal("replay barrier or membership missing")
	}
	frame := r23Next(t, c)
	if frame["type"] != "room_admitted" || frame["nonce"] != r23NonceB || frame["room"] != r23Room {
		t.Fatal("resume admission missing")
	}
}

func TestR23RejectInvalidResumeWithoutAck(t *testing.T) {
	h, ctx, cancel := r23Hub(t)
	c := r23Client(h, ctx, cancel, "one")
	raw := fmt.Sprintf(`{"type":"join","room":%q,"resume_token":"invalid","payload":{"admission_nonce":%q}}`, r23Room, r23NonceB)
	if err := r23Dispatch(c, raw); err != nil {
		t.Fatal("dispatch failed")
	}
	if frame := r23Next(t, c); frame["type"] != "error" || frame["code"] != "invalid_resume_token" {
		t.Fatal("legacy rejection changed")
	}
	r23Empty(t, c)
}

func TestR23AuthorizationMustFinishBeforeAck(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	gate := &r23BlockingAuth{started: make(chan struct{}), release: make(chan struct{})}
	h, err := NewHub(nil, slog.New(slog.NewTextHandler(io.Discard, nil)), gate, &config.Config{MaxClients: 10, BroadcastWorkers: 1}, nil)
	if err != nil {
		t.Fatal("hub setup failed")
	}
	h.sessionRevocationCheck = func(context.Context, string) error { return nil }
	t.Cleanup(func() { cancel(); h.Stop() })
	c := r23Client(h, ctx, cancel, "blocked")
	done := make(chan error, 1)
	go func() { done <- r23Dispatch(c, r23JoinRaw(r23NonceB)) }()
	select {
	case <-gate.started:
	case <-time.After(time.Second):
		t.Fatal("authorization did not start")
	}
	if c.isInRoom(r23Room) {
		t.Fatal("joined before authorization")
	}
	r23Empty(t, c)
	close(gate.release)
	select {
	case err := <-done:
		if err != nil {
			t.Fatal("join failed")
		}
	case <-time.After(time.Second):
		t.Fatal("join stalled")
	}
	if !c.isInRoom(r23Room) {
		t.Fatal("membership missing")
	}
	if frame := r23Next(t, c); frame["type"] != "room_admitted" || frame["nonce"] != r23NonceB {
		t.Fatal("ack missing")
	}
}

type r23BlockingAuth struct{ started, release chan struct{} }

func (a *r23BlockingAuth) CanJoinRoom(ctx context.Context, _, _ string) bool {
	close(a.started)
	select {
	case <-a.release:
		return true
	case <-ctx.Done():
		return false
	}
}
func (*r23BlockingAuth) Invalidate(string, string) {}

func TestR23QueuedAckIsRoomScopedBeforeRejoin(t *testing.T) {
	h, ctx, cancel := r23Hub(t)
	c := r23Client(h, ctx, cancel, "one")
	if err := r23Dispatch(c, r23JoinRaw(r23NonceB)); err != nil {
		t.Fatal("join failed")
	}
	var raw []byte
	select {
	case raw = <-c.Send:
	default:
		t.Fatal("ack missing")
	}
	room, scoped := queuedFrameRoom(raw)
	if !scoped || room != r23Room {
		t.Fatal("ack is not scoped")
	}
	if err := r23Dispatch(c, fmt.Sprintf(`{"type":"leave","room":%q}`, r23Room)); err != nil {
		t.Fatal("leave failed")
	}
	if c.shouldDeliverRoomFrame(room, scoped) {
		t.Fatal("ack deliverable after leave")
	}
}

func TestR23UnavailableResumeNeverClaimsAdmission(t *testing.T) {
	h, ctx, cancel := r23Hub(t)
	c := r23Client(h, ctx, cancel, "one")
	var secret [32]byte
	if _, err := rand.Read(secret[:]); err != nil {
		t.Fatal("random setup failed")
	}
	h.internalSecret = hex.EncodeToString(secret[:])
	h.chatStreamIncarnation = "synthetic-incarnation"
	h.streamChat = "CHAT_EVENTS"
	h.chatReplayAvailable.Store(false)
	token, err := h.issueResumeToken(c.UserID, r23Room, h.streamChat, 7)
	if err != nil {
		t.Fatal("resume setup failed")
	}
	raw := fmt.Sprintf(`{"type":"join","room":%q,"resume_token":%q,"payload":{"admission_nonce":%q}}`, r23Room, token, r23NonceB)
	if err := r23Dispatch(c, raw); err != nil {
		t.Fatal("dispatch failed")
	}
	if c.isInRoom(r23Room) {
		t.Fatal("unavailable replay joined")
	}
	if frame := r23Next(t, c); frame["type"] != "error" || frame["code"] != "replay_unavailable" {
		t.Fatal("unavailable rejection changed")
	}
	r23Empty(t, c)
}

func TestR23RevokedSessionCannotJoin(t *testing.T) {
	h, ctx, cancel := r23Hub(t)
	c := r23Client(h, ctx, cancel, "one")
	h.sessionRevocationCheck = func(context.Context, string) error { return errors.New("synthetic unavailable") }
	if err := r23Dispatch(c, r23JoinRaw(r23NonceB)); err == nil {
		t.Fatal("session error was ignored")
	}
	if c.isInRoom(r23Room) {
		t.Fatal("revoked session joined")
	}
	r23Empty(t, c)
}

type r23ScriptedSession struct{ frames [][]byte }

func (s *r23ScriptedSession) ReadMessage() (int, []byte, error) {
	if len(s.frames) == 0 {
		return 0, nil, io.EOF
	}
	data := s.frames[0]
	s.frames = s.frames[1:]
	return 1, data, nil
}
func (*r23ScriptedSession) WriteMessage(int, []byte) error    { return nil }
func (*r23ScriptedSession) Close() error                      { return nil }
func (*r23ScriptedSession) RemoteAddr() net.Addr              { return &net.TCPAddr{} }
func (*r23ScriptedSession) TransportType() string             { return "synthetic" }
func (*r23ScriptedSession) SetReadLimit(int64)                {}
func (*r23ScriptedSession) SetReadDeadline(time.Time) error   { return nil }
func (*r23ScriptedSession) SetWriteDeadline(time.Time) error  { return nil }
func (*r23ScriptedSession) SetPongHandler(func(string) error) {}

func TestR23SingleJoinConsumesOneRateTokenAndChecksSession(t *testing.T) {
	h, ctx, cancel := r23Hub(t)
	h.clientMsgRateLimit = 1e-9
	h.clientMsgRateBurst = 1
	var checks atomic.Int32
	h.sessionRevocationCheck = func(context.Context, string) error { checks.Add(1); return nil }
	c := r23Client(h, ctx, cancel, "one")
	c.Conn = &r23ScriptedSession{frames: [][]byte{[]byte(r23JoinRaw(r23NonceB)), []byte(fmt.Sprintf(`{"type":"heartbeat_ping","nonce":%q}`, r23NonceA))}}
	if !c.processNextMessage(ctx) || !c.isInRoom(r23Room) {
		t.Fatal("single join did not pass rate gate")
	}
	if frame := r23Next(t, c); frame["type"] != "room_admitted" || frame["nonce"] != r23NonceB {
		t.Fatal("admission missing")
	}
	if checks.Load() != 1 {
		t.Fatal("session check missing")
	}
	if !c.processNextMessage(ctx) {
		t.Fatal("rate rejection closed session")
	}
	if frame := r23Next(t, c); frame["type"] != "rate_limit_exceeded" {
		t.Fatal("subsequent frame bypassed rate gate")
	}
	if checks.Load() != 1 {
		t.Fatal("rate rejected frame reached session check")
	}
}

func TestR23DuplicateAndUnknownNonceRemainIneligibleAfterResumeMerge(t *testing.T) {
	for _, payload := range []string{
		fmt.Sprintf(`{"admission_nonce":%q,"admission_nonce":%q}`, r23NonceA, r23NonceB),
		fmt.Sprintf(`{"admission_nonce":%q,"unknown":true}`, r23NonceA),
	} {
		raw := fmt.Sprintf(`{"type":"join","room":%q,"resume_token":"synthetic","payload":%s}`, r23Room, payload)
		var msg Message
		if json.Unmarshal([]byte(raw), &msg) != nil {
			t.Fatal("decode failed")
		}
		mergeTopLevelJoinReplay(&msg, []byte(raw))
		var req joinPayload
		if json.Unmarshal(msg.Payload, &req) != nil || req.ResumeToken != "synthetic" {
			t.Fatal("legacy resume changed")
		}
		if admissionNonce(msg.Payload) != "" {
			t.Fatal("ambiguous opt-in accepted after merge")
		}
	}
}

func TestR23ReplayRateLimitDoesNotAcknowledge(t *testing.T) {
	h, ctx, cancel := r23Hub(t)
	c := r23Client(h, ctx, cancel, "one")
	var secret [32]byte
	if _, err := rand.Read(secret[:]); err != nil {
		t.Fatal("random setup failed")
	}
	h.internalSecret = hex.EncodeToString(secret[:])
	h.chatStreamIncarnation = "synthetic-incarnation"
	h.streamChat = "CHAT_EVENTS"
	h.chatReplayAvailable.Store(true)
	c.replayJoinLimiter = rate.NewLimiter(0, 0)
	token, err := h.issueResumeToken(c.UserID, r23Room, h.streamChat, 7)
	if err != nil {
		t.Fatal("resume setup failed")
	}
	raw := fmt.Sprintf(`{"type":"join","room":%q,"resume_token":%q,"payload":{"admission_nonce":%q}}`, r23Room, token, r23NonceB)
	if err := r23Dispatch(c, raw); err != nil {
		t.Fatal("dispatch failed")
	}
	if c.isInRoom(r23Room) {
		t.Fatal("rate-limited replay joined")
	}
	if frame := r23Next(t, c); frame["type"] != "error" || frame["code"] != "replay_join_rate_limited" {
		t.Fatal("rate-limit rejection changed")
	}
	r23Empty(t, c)
}

func TestR23AdmissionNonceStrictAndOptional(t *testing.T) {
	for _, payload := range []string{
		``, `null`, `[]`, `{}`, `{"admission_nonce":null}`,
		`{"`, `{"resume_token":`, fmt.Sprintf(`{"admission_nonce":%q`, r23NonceA), fmt.Sprintf(`{"admission_nonce":%q]`, r23NonceA),
		`{"admission_nonce":42}`, `{"admission_nonce":"short"}`,
		fmt.Sprintf(`{"admission_nonce":%q} {}`, r23NonceA),
		fmt.Sprintf(`{"admission_nonce":%q,"last_seq":"invalid"}`, r23NonceA),
		fmt.Sprintf(`{"admission_nonce":%q,"resume_token":42}`, r23NonceA),
		fmt.Sprintf(`{"admission_nonce":%q,"last_msg_id":42}`, r23NonceA),
		fmt.Sprintf(`{"admission_nonce":%q,"unknown":true}`, r23NonceA),
		fmt.Sprintf(`{"admission_nonce":%q,"admission_nonce":%q}`, r23NonceA, r23NonceB),
	} {
		if admissionNonce(json.RawMessage(payload)) != "" {
			t.Fatal("invalid opt-in accepted")
		}
	}
	payload := fmt.Sprintf(`{"admission_nonce":%q,"resume_token":"synthetic","last_seq":3,"last_msg_id":"synthetic"}`, r23NonceA)
	if admissionNonce(json.RawMessage(payload)) != r23NonceA {
		t.Fatal("valid optional fields rejected")
	}
}

func TestR23AckUsesExactAcceptedRoomBytes(t *testing.T) {
	h, ctx, cancel := r23Hub(t)
	for _, tc := range []struct {
		room      string
		expectAck bool
	}{
		{"AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA", true},
		{"not-a-uuid", false},
		{"zzzzzzzz-zzzz-4zzz-8zzz-zzzzzzzzzzzz", false},
	} {
		c := r23Client(h, ctx, cancel, "one")
		raw := fmt.Sprintf(`{"type":"join","room":%q,"payload":{"admission_nonce":%q}}`, tc.room, r23NonceB)
		if err := r23Dispatch(c, raw); err != nil || !c.isInRoom(tc.room) {
			t.Fatal("existing room admission changed")
		}
		if tc.expectAck {
			if frame := r23Next(t, c); frame["room"] != tc.room || frame["nonce"] != r23NonceB {
				t.Fatal("room bytes changed")
			}
		}
		r23Empty(t, c)
	}
}

func TestR23CannotAcknowledgeWithoutCurrentMembership(t *testing.T) {
	h, ctx, cancel := r23Hub(t)
	c := r23Client(h, ctx, cancel, "one")
	c.sendAdmissionAck(ctx, r23Room, r23NonceB)
	r23Empty(t, c)
}
