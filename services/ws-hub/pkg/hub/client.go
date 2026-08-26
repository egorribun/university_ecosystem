package hub

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/google/uuid"
	"github.com/gorilla/websocket"
	"github.com/nats-io/nats.go"
	"github.com/quic-go/webtransport-go"
	"golang.org/x/time/rate"
)

// ClientIdentity carries optional tenant context for a connected session.
type ClientIdentity struct {
	TenantID string
}

// Client represents a connected user session (WebSocket or WebTransport).
type Client struct {
	ID                string
	UserID            string
	Identity          *ClientIdentity
	Conn              Session
	Rooms             map[string]bool
	Send              chan []byte
	Hub               *Hub
	mu                sync.Mutex
	replayMu          sync.Mutex
	replays           map[string]*roomReplayState
	replayJoinLimiter *rate.Limiter
	closeOnce         sync.Once
	// ctx / cancel are tied to this connection's lifetime.
	ctx    context.Context
	cancel context.CancelFunc
}

type chEntry struct {
	closed bool
}

type roomReplayState struct {
	ctx           context.Context
	cancel        context.CancelFunc
	buffered      map[uint64][]byte
	bufferedBytes int
}

type roomEnqueueResult uint8

const (
	roomEnqueueDelivered roomEnqueueResult = iota
	roomEnqueueBuffered
	roomEnqueueBackpressured
	roomEnqueueReplayFatal
)

// writePumpPingInterval is a variable so the heartbeat branch can be exercised
// deterministically without making a test wait for the production 30-second
// interval. Production keeps the 30-second heartbeat contract.
var writePumpPingInterval = 30 * time.Second

var (
	chMutexes                = make(map[chan []byte]*chEntry)
	chMu                     sync.RWMutex
	safeSendAfterLockHook    = func(chan []byte, *chEntry) {}
	unsubscribePullFunc      = func(sub *nats.Subscription) error { return sub.Unsubscribe() }
	ackOfflineMessageFunc    = func(msg *nats.Msg) error { return msg.Ack() }
	nakOfflineMessageFunc    = func(msg *nats.Msg, delay time.Duration) error { return msg.NakWithDelay(delay) }
	termOfflineMessageFunc   = func(msg *nats.Msg) error { return msg.Term() }
	newReplayJoinLimiterFunc = func() *rate.Limiter {
		return rate.NewLimiter(rate.Every(time.Second), 2)
	}
	fetchPullMessagesFunc = func(sub *nats.Subscription, batch int, opts ...nats.PullOpt) ([]*nats.Msg, error) {
		return sub.Fetch(batch, opts...)
	}
)

const (
	offlineReplayBatchSize  = 100
	offlineReplayFetchWait  = time.Second
	offlineReplayRetryDelay = 5 * time.Second
	offlineReplaySendTries  = 4
	offlineReplaySendDelay  = 25 * time.Millisecond
	replayLiveBufferLimit   = 256
	replayLiveBufferBytes   = 4 * 1024 * 1024
)

// safeSend writes data to ch in a concurrency-safe manner without panicking if closed.
func safeSend(ch chan []byte, data []byte) (sent bool) {
	if ch == nil {
		return false
	}

	chMu.RLock()
	entry, ok := chMutexes[ch]
	if ok {
		defer func() {
			panicValue := recover()
			chMu.RUnlock()
			if panicValue != nil {
				sent = false
				chMu.Lock()
				if chMutexes[ch] == entry {
					delete(chMutexes, ch)
				}
				chMu.Unlock()
			}
		}()
		if entry.closed {
			return false
		}
		select {
		case ch <- data:
			return true
		default:
			return false
		}
	}
	chMu.RUnlock()

	// Register the channel under the exclusive lock only on its first send.
	// Re-check after acquiring it because another sender may have won the race.
	chMu.Lock()
	entry, ok = chMutexes[ch]
	if !ok {
		entry = &chEntry{}
		chMutexes[ch] = entry
	}
	defer func() {
		if recover() != nil {
			sent = false
			delete(chMutexes, ch)
		}
		chMu.Unlock()
	}()
	safeSendAfterLockHook(ch, entry)
	if entry.closed {
		return false
	}

	select {
	case ch <- data:
		return true
	default:
		return false
	}
}

// safeClose closes a channel in a data-race-free manner and cleans up channel map entry.
func safeClose(ch chan []byte) {
	if ch == nil {
		return
	}
	chMu.Lock()
	defer chMu.Unlock()

	entry, ok := chMutexes[ch]
	if ok && entry.closed {
		return
	}
	if ok {
		entry.closed = true
	}

	func() {
		defer func() {
			_ = recover() //nolint:errcheck // recover() returns interface{}; blank discard is the canonical pattern.
		}()
		close(ch)
	}()
	delete(chMutexes, ch)
}

func isNormalCloseError(err error) bool {
	if err == nil {
		return true
	}
	if errors.Is(err, io.EOF) || errors.Is(err, net.ErrClosed) {
		return true
	}
	if websocket.IsCloseError(err,
		websocket.CloseNormalClosure,
		websocket.CloseGoingAway,
		websocket.CloseNoStatusReceived,
		websocket.CloseAbnormalClosure) {
		return true
	}
	errStr := err.Error()
	if strings.Contains(errStr, "normal closure") ||
		strings.Contains(errStr, "NO_ERROR") ||
		strings.Contains(errStr, "application error 0x0") ||
		strings.Contains(errStr, "Application error 0x0") {
		return true
	}
	var sessErr *webtransport.SessionError
	if errors.As(err, &sessErr) && (sessErr.ErrorCode == 0 || sessErr.ErrorCode == 268) {
		return true
	}
	return false
}

func (c *Client) cleanupReadPump() {
	c.cancel()
	c.cancelAllRoomReplays()
	c.Hub.msgLimiters.Delete(c.ID)
	if c.Hub != nil {
		hCtx := c.Hub.Context()
		if hCtx != nil {
			select {
			case c.Hub.Unregister <- c:
			case <-hCtx.Done():
				c.closeOnce.Do(func() { safeClose(c.Send) })
			}
		} else {
			select {
			case c.Hub.Unregister <- c:
			default:
				c.closeOnce.Do(func() { safeClose(c.Send) })
			}
		}
	}
	if c.Conn != nil {
		if err := c.Conn.Close(); err != nil {
			c.Hub.Logger.ErrorContext(c.ctx, "Failed to close session connection", "client_id", c.ID, "err", err)
		}
	}
}

func (c *Client) setupConnection() {
	if c.Conn == nil {
		return
	}
	c.Conn.SetReadLimit(64 * 1024)
	if err := c.Conn.SetReadDeadline(time.Now().Add(60 * time.Second)); err != nil {
		c.Hub.Logger.ErrorContext(c.ctx, "Failed to set read deadline", "err", err)
	}
	c.Conn.SetPongHandler(func(string) error {
		if err := c.Conn.SetReadDeadline(time.Now().Add(60 * time.Second)); err != nil {
			c.Hub.Logger.ErrorContext(c.ctx, "Failed to update read deadline in pong handler", "err", err)
		}
		return nil
	})
}

func (c *Client) processNextMessage() bool {
	_, data, err := c.Conn.ReadMessage()
	if err != nil {
		if isNormalCloseError(err) {
			c.Hub.Logger.DebugContext(c.ctx, "Session closed normally", "client_id", c.ID)
		} else {
			c.Hub.Logger.WarnContext(c.ctx, "Session read error",
				"client_id", c.ID,
				"err", err)
		}
		return false
	}

	var msg Message
	if err := json.Unmarshal(data, &msg); err != nil {
		return true
	}

	// MOD-27-02: Validate message type at parse boundary
	if !isAllowedMessageType(msg.Type) {
		UnknownMsgTypeTotal.Inc()
		return true
	}
	mergeTopLevelJoinReplay(&msg, data)

	msg.From = c.UserID
	c.handleIncomingMessage(msg, data)
	return true
}

// ReadPump pumps messages from the session connection to the hub.
func (c *Client) ReadPump() {
	defer c.cleanupReadPump()
	c.setupConnection()

	for c.Conn != nil {
		if !c.processNextMessage() {
			break
		}
	}
}

func (c *Client) handleIncomingMessage(msg Message, data []byte) {
	switch msg.Type {
	case "join":
		c.handleJoin(msg)
	case "leave":
		c.handleLeave(msg)
	case "message":
		c.handleMessage(msg, data)
	default:
		// RZ-27-05: Log unknown message types for protocol drift detection.
		UnknownMsgTypeTotal.Inc()
		c.Hub.Logger.WarnContext(c.ctx, "Unknown message type",
			"client_id", c.ID, "type", msg.Type)
	}
}

type joinPayload struct {
	ResumeToken string `json:"resume_token,omitempty"`
	LastSeq     uint64 `json:"last_seq,omitempty"`
	LastMsgID   string `json:"last_msg_id,omitempty"`
}

func mergeTopLevelJoinReplay(msg *Message, data []byte) {
	if msg == nil || msg.Type != "join" {
		return
	}
	var topLevel joinPayload
	if err := json.Unmarshal(data, &topLevel); err != nil ||
		(topLevel.ResumeToken == "" && topLevel.LastSeq == 0 && topLevel.LastMsgID == "") {
		return
	}

	var payload joinPayload
	if len(msg.Payload) > 0 {
		if err := json.Unmarshal(msg.Payload, &payload); err != nil {
			return
		}
	}
	if payload.LastSeq == 0 {
		payload.LastSeq = topLevel.LastSeq
	}
	if payload.LastMsgID == "" {
		payload.LastMsgID = topLevel.LastMsgID
	}
	if payload.ResumeToken == "" {
		payload.ResumeToken = topLevel.ResumeToken
	}
	if merged, err := json.Marshal(payload); err == nil {
		msg.Payload = merged
	}
}

func (c *Client) handleJoin(msg Message) {
	if msg.Room == "" {
		return
	}
	if !c.Hub.AuthorizeRoomJoin(c.ctx, c.UserID, msg.Room) {
		AuthFailuresTotal.WithLabelValues("room_join_denied").Inc() // RZ-23-06: wire existing metric
		c.Hub.Logger.WarnContext(c.ctx, "Unauthorized room join rejected",
			"user", c.UserID,
			"room", msg.Room)
		return
	}
	var resumeToken string
	var legacyCursor bool
	if len(msg.Payload) > 0 {
		var jp joinPayload
		if err := json.Unmarshal(msg.Payload, &jp); err == nil {
			resumeToken = jp.ResumeToken
			legacyCursor = jp.LastSeq > 0 || jp.LastMsgID != ""
		}
	}

	if resumeToken != "" && c.Hub != nil && c.Hub.chatReplayAvailable.Load() {
		lastSeq, tokenErr := c.Hub.verifyResumeToken(resumeToken, c.UserID, msg.Room)
		if tokenErr != nil {
			c.JoinRoom(msg.Room)
			c.sendReplayJoinError(msg.Room, "invalid_resume_token", "resume token is invalid or expired")
			return
		}
		if !c.allowReplayJoin(msg.Room) {
			c.JoinRoom(msg.Room)
			return
		}
		c.startRoomReplay(msg.Room, lastSeq, "")
		return
	}
	c.cancelRoomReplay(msg.Room)
	c.JoinRoom(msg.Room)
	if legacyCursor && resumeToken == "" {
		c.sendReplayJoinError(msg.Room, "resume_token_required", "unsigned replay cursors are not accepted")
	}
}

func (c *Client) sendReplayJoinError(room, code, detail string) {
	frame, err := json.Marshal(map[string]string{
		"type": "error", "room": room, "code": code, "detail": detail,
	})
	if err == nil {
		_ = safeSend(c.Send, frame)
	}
}

func (c *Client) allowReplayJoin(room string) bool {
	c.replayMu.Lock()
	if c.replayJoinLimiter == nil {
		c.replayJoinLimiter = newReplayJoinLimiterFunc()
	}
	allowed := c.replayJoinLimiter.Allow()
	c.replayMu.Unlock()
	if allowed {
		return true
	}
	ReplayJoinRateLimitedTotal.Inc()
	c.sendReplayJoinError(room, "replay_join_rate_limited", "replay join rate limit exceeded")
	return false
}

//nolint:gocognit,cyclop
func (c *Client) startRoomReplay(room string, lastSeq uint64, lastMsgID string) {
	replayCtx, cancelReplay := context.WithCancel(c.ctx)
	state := &roomReplayState{
		ctx:      replayCtx,
		cancel:   cancelReplay,
		buffered: make(map[uint64][]byte),
	}
	c.replayMu.Lock()
	if c.replays == nil {
		c.replays = make(map[string]*roomReplayState)
	}
	if previous := c.replays[room]; previous != nil {
		previous.cancel()
	}
	c.replays[room] = state
	c.replayMu.Unlock()

	// Membership is established only after the replay barrier exists. Live
	// messages are then buffered by enqueueRoomBroadcast until replay drains.
	c.JoinRoom(room)
	go func() {
		maxSequence, completed := c.replayOfflineMessagesContext(
			replayCtx,
			room,
			lastSeq,
			lastMsgID,
		)
		if !completed {
			wasActive := replayCtx.Err() == nil
			if c.removeRoomReplay(room, state) && wasActive {
				c.failReplayConnection()
			}
			return
		}
		if !c.flushRoomReplay(room, state, maxSequence) && replayCtx.Err() == nil {
			c.failReplayConnection()
		}
	}()
}

func (c *Client) replayOfflineMessages(room string, lastSeq uint64, lastMsgID string) {
	_, _ = c.replayOfflineMessagesContext(c.ctx, room, lastSeq, lastMsgID)
}

func (c *Client) replayOfflineMessagesContext(
	replayCtx context.Context,
	room string,
	lastSeq uint64,
	lastMsgID string,
) (uint64, bool) {
	if c.Hub == nil || c.Hub.js == nil {
		return lastSeq, false
	}
	js := c.Hub.js

	var opts []nats.SubOpt
	streamName := c.Hub.streamChat
	if streamName == "" {
		streamName = "CHAT_EVENTS"
	}
	opts = append(opts, nats.BindStream(streamName))

	if lastSeq > 0 {
		opts = append(opts, nats.StartSequence(lastSeq+1))
	} else if lastMsgID != "" {
		if parsedSeq, err := strconv.ParseUint(lastMsgID, 10, 64); err == nil && parsedSeq > 0 {
			opts = append(opts, nats.StartSequence(parsedSeq+1))
		} else {
			opts = append(opts, nats.DeliverAll())
		}
	}

	sub, err := js.PullSubscribe("chat."+room, "", opts...)
	if err != nil {
		c.Hub.Logger.DebugContext(c.ctx, "Failed to create pull subscription for offline replay",
			"room", room, "err", err)
		return lastSeq, false
	}
	defer func() {
		if err := unsubscribePullFunc(sub); err != nil && c.Hub != nil && c.Hub.Logger != nil {
			c.Hub.Logger.DebugContext(c.ctx, "Failed to unsubscribe NATS pull sub", "err", err)
		}
	}()

	foundLastMsgID := (lastMsgID == "" || lastSeq > 0)
	maxSequence := lastSeq
	for {
		select {
		case <-replayCtx.Done():
			return maxSequence, false
		default:
		}

		fetchCtx, cancelFetch := context.WithTimeout(replayCtx, offlineReplayFetchWait)
		msgs, fetchErr := fetchPullMessagesFunc(
			sub,
			offlineReplayBatchSize,
			nats.Context(fetchCtx),
		)
		cancelFetch()
		if fetchErr != nil {
			if !errors.Is(fetchErr, nats.ErrTimeout) &&
				!errors.Is(fetchErr, context.DeadlineExceeded) &&
				!errors.Is(fetchErr, context.Canceled) {
				c.Hub.Logger.DebugContext(c.ctx, "Pull fetch for offline replay returned error",
					"room", room, "err", fetchErr)
			}
			return maxSequence,
				errors.Is(fetchErr, nats.ErrTimeout) || errors.Is(fetchErr, context.DeadlineExceeded)
		}
		if len(msgs) == 0 {
			return maxSequence, true
		}
		if !c.deliverOfflineMessageBatch(
			replayCtx,
			room,
			msgs,
			lastMsgID,
			&foundLastMsgID,
			&maxSequence,
		) {
			return maxSequence, false
		}
	}
}

func (c *Client) deliverOfflineMessages(msgs []*nats.Msg, lastSeq uint64, lastMsgID string) {
	foundLastMsgID := (lastMsgID == "" || lastSeq > 0)
	maxSequence := lastSeq
	room := ""
	if len(msgs) > 0 && msgs[0] != nil {
		room, _ = strings.CutPrefix(msgs[0].Subject, "chat.")
	}
	c.deliverOfflineMessageBatch(c.ctx, room, msgs, lastMsgID, &foundLastMsgID, &maxSequence)
}

func (c *Client) deliverOfflineMessageBatch(
	replayCtx context.Context,
	room string,
	msgs []*nats.Msg,
	lastMsgID string,
	foundLastMsgID *bool,
	maxSequence *uint64,
) bool {
	for _, m := range msgs {
		select {
		case <-replayCtx.Done():
			return false
		default:
		}

		msgID := ""
		if m.Header != nil {
			msgID = m.Header.Get("Nats-Msg-Id")
		}
		if !*foundLastMsgID {
			if msgID == lastMsgID {
				*foundLastMsgID = true
			}
			if err := ackOfflineMessageFunc(m); err != nil && c.Hub != nil && c.Hub.Logger != nil {
				c.Hub.Logger.DebugContext(c.ctx, "Failed to ack skipped NATS replay message", "err", err)
			}
			continue
		}

		var raw map[string]any
		decodeErr := json.Unmarshal(m.Data, &raw)
		metadata, metadataErr := m.Metadata()
		sequence := uint64(0)
		stream := ""
		if metadataErr == nil {
			sequence = metadata.Sequence.Stream
			stream = metadata.Stream
		}
		if decodeErr != nil || raw == nil || sequence == 0 {
			var checkpoint []byte
			if sequence > 0 && room != "" {
				if !chatSubjectMatchesRoom(m.Subject, room) {
					if err := termOfflineMessageFunc(m); err != nil {
						c.nakOfflineReplay(m)
						return false
					}
					continue
				}
				resumeToken, tokenErr := c.Hub.issueResumeToken(c.UserID, room, stream, sequence)
				if tokenErr != nil {
					return false
				}
				var checkpointErr error
				checkpoint, checkpointErr = json.Marshal(map[string]any{
					"type":         "replay_checkpoint",
					"room":         room,
					"seq":          sequence,
					"resume_token": resumeToken,
					"replayed":     true,
					"payload": map[string]any{
						"type":    "replay_checkpoint",
						"chat_id": room,
					},
				})
				if checkpointErr != nil {
					return false
				}
			}
			if err := termOfflineMessageFunc(m); err != nil {
				if c.Hub != nil && c.Hub.Logger != nil {
					c.Hub.Logger.DebugContext(c.ctx, "Failed to terminate invalid NATS replay message",
						"err", err, "metadata_err", metadataErr, "decode_err", decodeErr)
				}
				c.nakOfflineReplay(m)
				return false
			}
			if len(checkpoint) > 0 {
				if !c.sendReplayWithRetry(replayCtx, checkpoint) {
					c.nakOfflineReplay(m)
					return false
				}
				*maxSequence = max(*maxSequence, sequence)
			}
			continue
		}
		if !validateReplayChatBinding(m.Subject, room, raw) {
			if err := termOfflineMessageFunc(m); err != nil {
				c.nakOfflineReplay(m)
				return false
			}
			continue
		}
		resumeToken, tokenErr := c.Hub.issueResumeToken(c.UserID, room, stream, sequence)
		if tokenErr != nil {
			return false
		}

		raw["seq"] = sequence
		raw["replayed"] = true
		raw["resume_token"] = resumeToken
		data, marshalErr := json.Marshal(raw)
		if marshalErr != nil {
			if err := termOfflineMessageFunc(m); err != nil {
				c.nakOfflineReplay(m)
				return false
			}
			continue
		}
		if !c.sendReplayWithRetry(replayCtx, data) {
			c.nakOfflineReplay(m)
			return false
		}
		*maxSequence = max(*maxSequence, sequence)
		JetStreamReplayedTotal.Inc()
		if err := ackOfflineMessageFunc(m); err != nil && c.Hub != nil && c.Hub.Logger != nil {
			c.Hub.Logger.DebugContext(c.ctx, "Failed to ack queued NATS replay message", "err", err)
		}
	}
	return true
}

func (c *Client) sendReplayWithRetry(ctx context.Context, data []byte) bool {
	for attempt := 0; attempt < offlineReplaySendTries; attempt++ {
		if safeSend(c.Send, data) {
			return true
		}
		if attempt+1 == offlineReplaySendTries {
			return false
		}
		delay := offlineReplaySendDelay << attempt
		timer := time.NewTimer(delay)
		select {
		case <-ctx.Done():
			if !timer.Stop() {
				<-timer.C
			}
			return false
		case <-timer.C:
		}
	}
	return false
}

func (c *Client) nakOfflineReplay(msg *nats.Msg) {
	if err := nakOfflineMessageFunc(msg, offlineReplayRetryDelay); err != nil && c.Hub != nil && c.Hub.Logger != nil {
		c.Hub.Logger.DebugContext(c.ctx, "Failed to NAK backpressured NATS replay message", "err", err)
	}
}

func (c *Client) enqueueRoomBroadcast(msg *Message, data []byte) roomEnqueueResult {
	if c.ctx != nil && c.ctx.Err() != nil {
		return roomEnqueueReplayFatal
	}
	if msg == nil || msg.Room == "" {
		if safeSend(c.Send, data) {
			return roomEnqueueDelivered
		}
		return roomEnqueueBackpressured
	}
	if msg.Seq > 0 {
		resumeToken, err := c.Hub.issueResumeToken(c.UserID, msg.Room, msg.Stream, msg.Seq)
		if err != nil {
			return roomEnqueueReplayFatal
		}
		var frame map[string]any
		if err := json.Unmarshal(data, &frame); err != nil || frame == nil {
			return roomEnqueueReplayFatal
		}
		frame["resume_token"] = resumeToken
		personalized, err := json.Marshal(frame)
		if err != nil {
			return roomEnqueueReplayFatal
		}
		data = personalized
	}

	c.replayMu.Lock()
	state := c.replays[msg.Room]
	if state == nil {
		c.replayMu.Unlock()
		if safeSend(c.Send, data) {
			return roomEnqueueDelivered
		}
		return roomEnqueueBackpressured
	}
	if msg.Seq == 0 {
		state.cancel()
		delete(c.replays, msg.Room)
		c.replayMu.Unlock()
		return roomEnqueueReplayFatal
	}
	existing, exists := state.buffered[msg.Seq]
	projectedBytes := state.bufferedBytes + len(data)
	if exists {
		projectedBytes -= len(existing)
	}
	if (!exists && len(state.buffered) >= replayLiveBufferLimit) ||
		projectedBytes > replayLiveBufferBytes {
		state.cancel()
		delete(c.replays, msg.Room)
		c.replayMu.Unlock()
		return roomEnqueueReplayFatal
	}
	state.buffered[msg.Seq] = append([]byte(nil), data...)
	state.bufferedBytes = projectedBytes
	c.replayMu.Unlock()
	return roomEnqueueBuffered
}

func (c *Client) flushRoomReplay(room string, state *roomReplayState, maxSequence uint64) bool {
	for {
		c.replayMu.Lock()
		if c.replays[room] != state {
			c.replayMu.Unlock()
			return false
		}
		sequences := make([]uint64, 0, len(state.buffered))
		for sequence, data := range state.buffered {
			if sequence > maxSequence {
				sequences = append(sequences, sequence)
				continue
			}
			delete(state.buffered, sequence)
			state.bufferedBytes -= len(data)
		}
		if len(sequences) == 0 {
			delete(c.replays, room)
			state.cancel()
			c.replayMu.Unlock()
			return true
		}
		sort.Slice(sequences, func(i, j int) bool { return sequences[i] < sequences[j] })
		batch := make([][]byte, 0, len(sequences))
		for _, sequence := range sequences {
			data := state.buffered[sequence]
			batch = append(batch, data)
			delete(state.buffered, sequence)
			state.bufferedBytes -= len(data)
		}
		c.replayMu.Unlock()

		for index, data := range batch {
			if !c.sendReplayWithRetry(state.ctx, data) {
				c.detachRoomReplay(room, state)
				return false
			}
			maxSequence = sequences[index]
			MessagesDeliveredTotal.Inc()
		}
	}
}

func (c *Client) detachRoomReplay(room string, state *roomReplayState) bool {
	c.replayMu.Lock()
	defer c.replayMu.Unlock()
	if c.replays[room] != state {
		return false
	}
	delete(c.replays, room)
	return true
}

func (c *Client) removeRoomReplay(room string, state *roomReplayState) bool {
	c.replayMu.Lock()
	defer c.replayMu.Unlock()
	if c.replays[room] != state {
		return false
	}
	delete(c.replays, room)
	state.cancel()
	return true
}

func (c *Client) cancelRoomReplay(room string) {
	c.replayMu.Lock()
	if state := c.replays[room]; state != nil {
		delete(c.replays, room)
		state.cancel()
	}
	c.replayMu.Unlock()
}

func (c *Client) cancelAllRoomReplays() {
	c.replayMu.Lock()
	for room, state := range c.replays {
		delete(c.replays, room)
		state.cancel()
	}
	c.replayMu.Unlock()
}

func (c *Client) failReplayConnection() {
	if c.cancel != nil {
		c.cancel()
	}
	if c.Conn != nil {
		_ = c.Conn.Close()
	}
	if c.Hub == nil {
		return
	}
	select {
	case c.Hub.Unregister <- c:
	default:
		c.closeOnce.Do(func() { safeClose(c.Send) })
	}
}

func (c *Client) handleLeave(msg Message) {
	c.LeaveRoom(msg.Room)
}

var allowedMessageTypes = map[string]bool{
	"join":    true,
	"leave":   true,
	"message": true,
}

func isAllowedMessageType(t string) bool {
	return allowedMessageTypes[t]
}

//nolint:cyclop
func (c *Client) handleMessage(msg Message, data []byte) {
	// RZ-27-02: Reject oversized messages at ingress, matching the broadcast
	// limit (RZ-23-05). Without this, messages between 60 KB and 64 KB are
	// published to NATS but silently dropped at broadcast fan-out.
	const maxIncomingBytes = 60 * 1024 // match maxBroadcastBytes in hub.go
	if len(data) > maxIncomingBytes {
		c.Hub.Logger.WarnContext(c.ctx, "Incoming message exceeds size limit, notifying client",
			"client_id", c.ID, "size_bytes", len(data), "limit_bytes", maxIncomingBytes)
		IncomingDropsTotal.Inc()
		// RZ-31-02: Notify client so it can display a user-visible error.
		// Follows the same pattern as rate-limit notification below (lines 166-171).
		if notice, err := json.Marshal(map[string]string{
			"type":   "error",
			"code":   "message_too_large",
			"detail": "message exceeds 60 KB limit",
		}); err == nil {
			select {
			case c.Send <- notice:
			default: // Send buffer full — client already overwhelmed.
			}
		}
		return
	}

	if msg.Room == "" || !c.isInRoom(msg.Room) {
		AuthFailuresTotal.WithLabelValues("room_message_denied").Inc()
		c.Hub.Logger.WarnContext(c.ctx, "Unauthorized room message rejected",
			"client_id", c.ID, "user_id", c.UserID, "room", msg.Room)
		return
	}

	// TD-W16-03 / RZ-W18-01: Use configurable rate limit fields copied to Hub struct.
	raw, _ := c.Hub.msgLimiters.LoadOrStore(c.ID,
		rate.NewLimiter(rate.Limit(c.Hub.clientMsgRateLimit), c.Hub.clientMsgRateBurst))
	if !raw.(*rate.Limiter).Allow() {
		c.Hub.Logger.WarnContext(c.ctx, "Client message rate limit exceeded — notifying client",
			"client_id", c.ID,
			"room", msg.Room)
		if notice, err := json.Marshal(map[string]string{"type": "rate_limit_exceeded"}); err == nil {
			select {
			case c.Send <- notice:
			default:
				// Send buffer full — client is already overwhelmed; drop silently.
			}
		}
		return
	}

	if c.Hub == nil || c.Hub.Nats == nil {
		return
	}

	// Sender identity is always derived from the authenticated connection.
	// Publish the canonical structure rather than the original attacker bytes.
	msg.From = c.UserID
	canonicalData, err := json.Marshal(msg)
	if err != nil {
		c.Hub.Logger.ErrorContext(c.ctx, "Failed to encode canonical client message", "err", err)
		return
	}

	msgID := uuid.New().String()
	natsMsg := &nats.Msg{
		Subject: "chat." + msg.Room,
		Data:    canonicalData,
		Header:  make(nats.Header),
	}
	natsMsg.Header.Set("Nats-Msg-Id", msgID)

	if c.Hub.enableJetStream && c.Hub.js != nil {
		if _, err := c.Hub.js.PublishMsgAsync(natsMsg); err != nil {
			if c.Hub.Logger != nil {
				c.Hub.Logger.ErrorContext(c.ctx, "Failed to publish async to JetStream", "err", err)
			}
		}
	} else {
		// Core NATS does not provide JetStream de-duplication and older servers
		// may not negotiate headers. Publish the canonical payload without the
		// JetStream-only Nats-Msg-Id header on the fallback transport.
		if err := c.Hub.Nats.Publish(natsMsg.Subject, natsMsg.Data); err != nil {
			if c.Hub.Logger != nil {
				c.Hub.Logger.ErrorContext(c.ctx, "Failed to publish to NATS", "err", err)
			}
		}
	}
}

func (c *Client) isInRoom(room string) bool {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.Rooms[room]
}

// WritePump pumps messages from the hub to the session connection.
//
//nolint:gocognit,cyclop
func (c *Client) WritePump() {
	ticker := time.NewTicker(writePumpPingInterval)
	defer func() {
		ticker.Stop()
		c.Hub.msgLimiters.Delete(c.ID) // TD-24-05: clean limiter on WritePump exit too
		if c.Conn != nil {
			if err := c.Conn.Close(); err != nil {
				c.Hub.Logger.ErrorContext(c.ctx, "Failed to close session connection in WritePump", "err", err)
			}
		}
	}()

	for {
		select {
		case msg, ok := <-c.Send:
			if c.Conn != nil {
				if err := c.Conn.SetWriteDeadline(time.Now().Add(10 * time.Second)); err != nil {
					c.Hub.Logger.ErrorContext(c.ctx, "Failed to set write deadline", "err", err)
				}
			}
			if !ok {
				if c.Conn != nil {
					if err := c.Conn.WriteMessage(websocket.CloseMessage, []byte{}); err != nil {
						c.Hub.Logger.ErrorContext(c.ctx, "Failed to write close message", "err", err)
					}
				}
				return
			}

			if c.Conn != nil {
				if err := c.Conn.WriteMessage(websocket.TextMessage, msg); err != nil {
					return
				}
			}

		case <-c.ctx.Done():
			// RZ-26-08: context cancelled (ReadPump exited) — stop immediately
			return

		case <-ticker.C:
			if c.Conn != nil {
				if err := c.Conn.SetWriteDeadline(time.Now().Add(10 * time.Second)); err != nil {
					c.Hub.Logger.ErrorContext(c.ctx, "Failed to set write deadline for ping", "err", err)
				}
				if err := c.Conn.WriteMessage(websocket.PingMessage, nil); err != nil {
					return
				}
			}
		}
	}
}

// JoinRoom adds the client to the specified room.
func (c *Client) JoinRoom(room string) {
	if room == "" {
		return
	}

	c.Hub.mu.Lock()
	defer c.Hub.mu.Unlock()

	c.mu.Lock()
	c.Rooms[room] = true
	c.mu.Unlock()

	if c.Hub.Rooms[room] == nil {
		c.Hub.Rooms[room] = make(map[*Client]bool)
	}
	c.Hub.Rooms[room][c] = true

	c.Hub.Logger.DebugContext(c.ctx, "Client joined room", "client", c.ID, "room", room)
}

// LeaveRoom removes the client from the specified room.
func (c *Client) LeaveRoom(room string) {
	if room == "" {
		return
	}
	c.cancelRoomReplay(room)

	c.Hub.mu.Lock()
	defer c.Hub.mu.Unlock()

	c.mu.Lock()
	delete(c.Rooms, room)
	c.mu.Unlock()

	if clients, ok := c.Hub.Rooms[room]; ok {
		delete(clients, c)
		if len(clients) == 0 {
			delete(c.Hub.Rooms, room)
		}
	}
}

// Disconnect sends a WebSocket close control frame with the specified close code and reason,
// then enqueues the client into Hub.Unregister for clean channel/room teardown.
func (c *Client) Disconnect(closeCode int, reason string) {
	c.cancelAllRoomReplays()
	if c.Conn != nil {
		closeMsg := websocket.FormatCloseMessage(closeCode, reason)
		if err := c.Conn.SetWriteDeadline(time.Now().Add(5 * time.Second)); err != nil && c.Hub != nil && c.Hub.Logger != nil {
			c.Hub.Logger.DebugContext(c.ctx, "Failed to set write deadline on disconnect", "err", err)
		}
		if err := c.Conn.WriteMessage(websocket.CloseMessage, closeMsg); err != nil {
			if c.Hub != nil && c.Hub.Logger != nil {
				c.Hub.Logger.WarnContext(c.ctx, "Failed to write close control frame to client",
					"client_id", c.ID, "user_id", c.UserID, "err", err)
			}
		}
	}

	if c.Hub != nil {
		hCtx := c.Hub.Context()
		if hCtx != nil {
			select {
			case c.Hub.Unregister <- c:
			case <-hCtx.Done():
				c.closeOnce.Do(func() { safeClose(c.Send) })
			}
		} else {
			select {
			case c.Hub.Unregister <- c:
			default:
				c.closeOnce.Do(func() { safeClose(c.Send) })
			}
		}
	}
}
